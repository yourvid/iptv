#!/usr/bin/env python3
"""
组播节目扫描器 - 严格流验证版本
按照IP和端口排序输出结果
"""

import socket
import time
import argparse
import ipaddress
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests


class MulticastStreamValidator:
    def __init__(self, base_url="http://192.168.5.2:5140/rtp/", timeout=8, max_workers=8):
        self.base_url = base_url.rstrip('/') + '/'
        self.timeout = timeout
        self.max_workers = max_workers
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'VLC/3.0.0 LibVLC/3.0.0',
        })

    def validate_stream_strict(self, multicast_addr, port=5140):
        """
        严格验证组播流是否真正有效
        直接检查流数据内容
        """
        stream_url = f"{self.base_url}{multicast_addr}:{port}"

        print(f"🔍 验证: {multicast_addr}:{port}")

        try:
            # 直接进行GET请求，获取实际数据
            start_time = time.time()
            response = self.session.get(
                stream_url,
                timeout=self.timeout,
                stream=True
            )
            connect_time = time.time() - start_time

            if response.status_code != 200:
                print(f"  ❌ HTTP {response.status_code}: {multicast_addr}:{port}")
                response.close()
                return {
                    'multicast_addr': multicast_addr,
                    'port': port,
                    'url': stream_url,
                    'status': 'invalid',
                    'error': f'HTTP {response.status_code}',
                    'response_time': round(connect_time, 3)
                }

            # 检查响应头信息
            content_type = response.headers.get('Content-Type', '').lower()
            content_length = response.headers.get('Content-Length')
            server_info = response.headers.get('Server', '')

            print(f"  📊 响应头 - 类型: {content_type}, 长度: {content_length}")

            # 尝试读取数据来验证流是否真实
            data_valid = False
            data_size = 0
            chunk_count = 0
            start_read_time = time.time()

            # 读取前几个数据块来验证
            for chunk in response.iter_content(chunk_size=4096):
                if chunk:
                    data_size += len(chunk)
                    chunk_count += 1

                    # 如果有实际数据，认为流可能有效
                    if data_size > 100:  # 至少收到100字节数据
                        data_valid = True
                        break

                    # 最多读取3个块或32KB数据
                    if chunk_count >= 3 or data_size >= 32768:
                        break

            read_time = time.time() - start_read_time
            total_time = time.time() - start_time
            response.close()

            # 判断流是否有效
            if data_valid and data_size > 0:
                print(f"  ✅ 有效流: {multicast_addr}:{port} - 收到 {data_size} 字节数据")
                return {
                    'multicast_addr': multicast_addr,
                    'port': port,
                    'url': stream_url,
                    'status': 'available',
                    'response_time': round(total_time, 3),
                    'data_received': data_size,
                    'content_type': content_type,
                    'chunks_received': chunk_count,
                    'server': server_info
                }
            else:
                print(f"  ❌ 无数据: {multicast_addr}:{port} - 仅 {data_size} 字节")
                return {
                    'multicast_addr': multicast_addr,
                    'port': port,
                    'url': stream_url,
                    'status': 'no_data',
                    'error': f'无有效数据，仅收到 {data_size} 字节',
                    'response_time': round(total_time, 3),
                    'data_received': data_size
                }

        except requests.exceptions.ConnectTimeout:
            print(f"  ⏰ 连接超时: {multicast_addr}:{port}")
            return {
                'multicast_addr': multicast_addr,
                'port': port,
                'url': stream_url,
                'status': 'timeout',
                'error': '连接超时'
            }
        except requests.exceptions.ConnectionError:
            print(f"  🔌 连接拒绝: {multicast_addr}:{port}")
            return {
                'multicast_addr': multicast_addr,
                'port': port,
                'url': stream_url,
                'status': 'connection_refused',
                'error': '连接被拒绝'
            }
        except requests.exceptions.ReadTimeout:
            print(f"  ⏰ 读取超时: {multicast_addr}:{port}")
            return {
                'multicast_addr': multicast_addr,
                'port': port,
                'url': stream_url,
                'status': 'read_timeout',
                'error': '读取超时'
            }
        except Exception as e:
            print(f"  💥 错误: {multicast_addr}:{port} - {str(e)}")
            return {
                'multicast_addr': multicast_addr,
                'port': port,
                'url': stream_url,
                'status': 'error',
                'error': str(e)
            }

    def scan_range(self, start_addr, end_addr, ports=[5140], output_file=None):
        """
        扫描指定范围内的组播地址
        """
        print(f"🎯 开始严格扫描组播地址范围: {start_addr} - {end_addr}")
        print(f"🌐 基础URL: {self.base_url}")
        print(f"🔌 扫描端口: {ports}")
        print(f"⏱️  超时时间: {self.timeout}秒")
        print(f"👥 工作线程: {self.max_workers}")
        print("-" * 60)

        # 生成要扫描的地址列表
        targets = []
        start_ip = ipaddress.IPv4Address(start_addr)
        end_ip = ipaddress.IPv4Address(end_addr)

        for ip_int in range(int(start_ip), int(end_ip) + 1):
            ip_addr = str(ipaddress.IPv4Address(ip_int))
            for port in ports:
                targets.append((ip_addr, port))

        total_targets = len(targets)
        print(f"📋 总共需要扫描 {total_targets} 个目标")

        return self._scan_targets(targets, output_file)

    def _scan_targets(self, targets, output_file=None):
        """扫描目标列表"""
        total_targets = len(targets)
        completed = 0
        available_streams = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任务
            future_to_target = {
                executor.submit(self.validate_stream_strict, addr, port): (addr, port)
                for addr, port in targets
            }

            # 处理完成的任务
            for future in as_completed(future_to_target):
                addr, port = future_to_target[future]
                completed += 1

                try:
                    result = future.result()

                    if result['status'] == 'available':
                        available_streams.append(result)
                        print(f"🎉 发现有效流: {result['url']}")
                        print(f"   数据量: {result['data_received']} 字节, "
                              f"响应时间: {result['response_time']}s")

                except Exception as e:
                    print(f"💥 处理异常: {addr}:{port} - {str(e)}")

                # 显示进度
                if completed % 1 == 0 or completed == total_targets:
                    print(f"📊 进度: {completed}/{total_targets} ({completed / total_targets * 100:.1f}%) - "
                          f"已发现 {len(available_streams)} 个有效流")

        # 按照IP和端口排序
        available_streams = self._sort_results(available_streams)

        # 输出最终结果
        print("\n" + "=" * 60)
        print("🎉 扫描完成!")
        print(f"📋 扫描统计:")
        print(f"   总共扫描: {total_targets} 个目标")
        print(f"   有效流: {len(available_streams)} 个")

        # 打印排序后的可用流详情
        if available_streams:
            print(f"\n🎯 发现的有效组播流 (按IP和端口排序):")
            self._print_sorted_results(available_streams)
        else:
            print(f"\n❌ 未发现有效的组播流")
            print(f"💡 建议:")
            print(f"  1. 检查网络连接和基础URL")
            print(f"  2. 确认组播服务器运行正常")
            print(f"  3. 尝试调整扫描范围和端口")

        # 保存排序后的结果到文件
        if output_file and available_streams:
            self.save_results(available_streams, output_file)

        return available_streams

    def _sort_results(self, results):
        """
        按照IP地址和端口号排序结果
        先按IP地址排序，再按端口号排序
        """

        def sort_key(item):
            # 将IP地址转换为整数用于排序
            ip_parts = list(map(int, item['multicast_addr'].split('.')))
            port = item['port']
            # 返回一个元组，先按IP排序，再按端口排序
            return (ip_parts[0], ip_parts[1], ip_parts[2], ip_parts[3], port)

        return sorted(results, key=sort_key)

    def _print_sorted_results(self, results):
        """
        打印排序后的结果，按IP段分组显示
        """
        current_ip_prefix = None

        for i, result in enumerate(results, 1):
            ip_addr = result['multicast_addr']
            port = result['port']

            # 按IP地址的前三段分组
            ip_prefix = '.'.join(ip_addr.split('.')[:3])

            # 如果IP段变化，打印分隔线
            if ip_prefix != current_ip_prefix:
                if current_ip_prefix is not None:
                    print()
                current_ip_prefix = ip_prefix
                print(f"  📡 IP段: {ip_prefix}.*")

            print(f"     {i:2d}. {ip_addr}:{port}")
            print(f"         URL: {result['url']}")
            print(f"         数据: {result['data_received']} 字节, "
                  f"响应: {result['response_time']}s")

    def save_results(self, results, filename):
        """保存排序后的结果到文件"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write("# 组播节目扫描结果 - 严格验证\n")
                f.write(f"# 扫描时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                # f.write(f"# 基础URL: {self.base_url}\n")
                f.write(f"# 发现 {len(results)} 个有效流\n")
                f.write("# 按IP地址和端口排序\n")
                f.write("#" * 50 + "\n")

                f.write("#EXTM3U\n")
                current_ip_prefix = None
                index = 1
                for result in results:
                    ip_addr = result['multicast_addr']
                    ip_prefix = '.'.join(ip_addr.split('.')[:3])

                    # 按IP段分组
                    if ip_prefix != current_ip_prefix:
                        if current_ip_prefix is not None:
                            f.write("\n")
                        current_ip_prefix = ip_prefix
                        # f.write(f"# IP段: {ip_prefix}.*\n")

                    # f.write(f"# {ip_addr}:{result['port']}\n")
                    # f.write(f"# 数据: {result['data_received']} 字节, "
                    #         f"响应: {result['response_time']}s\n")
                    f.write(f"#EXTINF:-1 tvg-id=\"{index}\" tvg-name=\"{index}\" group-title=\"全部\",{index}\n")
                    f.write(f"{result['url']}\n\n")
                    index += 1

            print(f"💾 结果已保存到: {filename}")
        except Exception as e:
            print(f"❌ 保存文件时出错: {str(e)}")


def main():
    parser = argparse.ArgumentParser(description='组播节目扫描器 - 严格验证版')

    parser.add_argument('--base-url', default='http://192.168.5.2:5140/rtp/',
                        help='组播转单播的基础URL')
    parser.add_argument('--start', default='239.0.0.1',
                        help='起始组播地址')
    parser.add_argument('--end', default='239.0.0.255',
                        help='结束组播地址')
    parser.add_argument('--ports', default='5140',
                        help='要扫描的端口，多个端口用逗号分隔')
    parser.add_argument('--timeout', type=float, default=8,
                        help='请求超时时间（秒）')
    parser.add_argument('--workers', type=int, default=8,
                        help='并发工作线程数')
    parser.add_argument('--output', help='输出文件路径', default='iptvscanner.txt')

    args = parser.parse_args()

    # 解析端口
    ports = [int(port.strip()) for port in args.ports.split(',')]

    # 创建扫描器
    scanner = MulticastStreamValidator(
        base_url=args.base_url,
        timeout=args.timeout,
        max_workers=args.workers
    )

    # 执行扫描
    try:
        print("🚀 启动严格组播流验证扫描器...")
        results = scanner.scan_range(
            start_addr=args.start,
            end_addr=args.end,
            ports=ports,
            output_file=args.output
        )

    except KeyboardInterrupt:
        print("\n⏹️  扫描被用户中断")
    except Exception as e:
        print(f"💥 扫描过程中发生错误: {str(e)}")


if __name__ == "__main__":
    main()