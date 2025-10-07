#!/usr/bin/env python3
"""
M3U文件对比工具
对比两个M3U文件，找出只在一个文件中存在的URL
"""

import re
import argparse
from collections import defaultdict


class M3UComparator:
    def __init__(self):
        self.url_pattern = re.compile(r'^(http?://[^\s]+)$')
        self.extinf_pattern = re.compile(r'^#EXTINF:')

    def parse_m3u_file(self, file_path):
        """
        解析M3U文件，返回URL列表和频道信息

        Returns:
            dict: {
                'urls': set(),  # 所有URL的集合
                'channels': []  # 频道信息列表
            }
        """
        print(f"📖 正在解析文件: {file_path}")

        channels = []
        current_channel = {}

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            for line_num, line in enumerate(lines, 1):
                line = line.strip()

                if not line:
                    continue

                # 处理 #EXTINF 行
                if line.startswith('#EXTINF:'):
                    current_channel = {
                        'extinf': line,
                        'line_number': line_num,
                        'file': file_path
                    }

                # 处理URL行
                elif self.url_pattern.match(line):
                    if current_channel:
                        current_channel['url'] = line
                        channels.append(current_channel)
                        current_channel = {}
                    else:
                        # 如果没有EXTINF行，直接记录URL
                        channels.append({
                            'url': line,
                            'extinf': '',
                            'line_number': line_num,
                            'file': file_path
                        })

                # 处理其他元数据行（如#EXTM3U等）
                elif line.startswith('#'):
                    if 'extinf' not in current_channel:
                        current_channel['metadata'] = line

            print(f"✅ 成功解析 {len(channels)} 个频道")
            return {
                'urls': {channel['url'] for channel in channels},
                'channels': channels
            }

        except FileNotFoundError:
            print(f"❌ 文件不存在: {file_path}")
            return {'urls': set(), 'channels': []}
        except Exception as e:
            print(f"❌ 解析文件时出错: {file_path} - {str(e)}")
            return {'urls': set(), 'channels': []}

    def extract_channel_name(self, extinf_line):
        """从EXTINF行中提取频道名称"""
        if not extinf_line:
            return "未知频道"

        # 尝试提取频道名称（最后一个逗号后的内容）
        parts = extinf_line.split(',')
        if len(parts) > 1:
            return parts[-1].strip()

        # 尝试从tvg-name属性提取
        tvg_name_match = re.search(r'tvg-name="([^"]*)"', extinf_line)
        if tvg_name_match:
            return tvg_name_match.group(1)

        return "未知频道"

    def compare_files(self, file1, file2, output_file=None):
        """
        对比两个M3U文件

        Args:
            file1: 第一个M3U文件路径
            file2: 第二个M3U文件路径
            output_file: 输出结果文件路径
        """
        print("🔍 开始对比M3U文件...")
        print("=" * 60)

        # 解析两个文件
        data1 = self.parse_m3u_file(file1)
        data2 = self.parse_m3u_file(file2)

        urls1 = data1['urls']
        urls2 = data2['urls']
        channels1 = data1['channels']
        channels2 = data2['channels']

        print(f"\n📊 文件统计:")
        print(f"  {file1}: {len(urls1)} 个频道")
        print(f"  {file2}: {len(urls2)} 个频道")

        # 找出差异
        only_in_file1 = urls1 - urls2
        only_in_file2 = urls2 - urls1
        common_urls = urls1 & urls2

        print(f"\n📈 对比结果:")
        print(f"  只在 {file1} 中的频道: {len(only_in_file1)} 个")
        print(f"  只在 {file2} 中的频道: {len(only_in_file2)} 个")
        print(f"  两个文件共有的频道: {len(common_urls)} 个")

        # 获取详细的频道信息
        only_in_file1_details = [ch for ch in channels1 if ch['url'] in only_in_file1]
        only_in_file2_details = [ch for ch in channels2 if ch['url'] in only_in_file2]

        # 按频道名称排序
        only_in_file1_details.sort(key=lambda x: self.extract_channel_name(x['extinf']))
        only_in_file2_details.sort(key=lambda x: self.extract_channel_name(x['extinf']))

        # 输出结果
        self._print_comparison_results(
            only_in_file1_details, only_in_file2_details,
            file1, file2, output_file
        )

        return {
            'only_in_file1': only_in_file1_details,
            'only_in_file2': only_in_file2_details,
            'common': common_urls
        }

    def _print_comparison_results(self, only1, only2, file1, file2, output_file):
        """打印对比结果"""
        print("\n" + "=" * 60)

        # 输出只在文件1中的频道
        if only1:
            print(f"\n📺 只在 {file1} 中的频道 ({len(only1)} 个):")
            print("-" * 50)
            for i, channel in enumerate(only1, 1):
                channel_name = self.extract_channel_name(channel['extinf'])
                print(f"{i:2d}. {channel_name}")
                print(f"    URL: {channel['url']}")
                if channel['extinf']:
                    print(f"    信息: {channel['extinf'][:80]}...")
                print()
        else:
            print(f"\n📭 {file1} 中没有独有的频道")

        # 输出只在文件2中的频道
        if only2:
            print(f"\n📺 只在 {file2} 中的频道 ({len(only2)} 个):")
            print("-" * 50)
            for i, channel in enumerate(only2, 1):
                channel_name = self.extract_channel_name(channel['extinf'])
                print(f"{i:2d}. {channel_name}")
                print(f"    URL: {channel['url']}")
                if channel['extinf']:
                    print(f"    信息: {channel['extinf'][:80]}...")
                print()
        else:
            print(f"\n📭 {file2} 中没有独有的频道")

        # 保存结果到文件
        if output_file:
            self._save_comparison_results(only1, only2, file1, file2, output_file)

    def _save_comparison_results(self, only1, only2, file1, file2, output_file):
        """保存对比结果到文件"""
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write("# M3U文件对比结果\n")
                f.write(f"# 对比文件: {file1} vs {file2}\n")
                f.write(f"# 生成时间: {self._get_current_time()}\n")
                f.write("#" * 60 + "\n\n")

                # 保存只在文件1中的频道
                if only1:
                    f.write(f"# 只在 {file1} 中的频道 ({len(only1)} 个)\n")
                    f.write("#" * 50 + "\n")
                    for channel in only1:
                        if channel['extinf']:
                            f.write(f"{channel['extinf']}\n")
                        f.write(f"{channel['url']}\n\n")

                # 保存只在文件2中的频道
                if only2:
                    f.write(f"# 只在 {file2} 中的频道 ({len(only2)} 个)\n")
                    f.write("#" * 50 + "\n")
                    for channel in only2:
                        if channel['extinf']:
                            f.write(f"{channel['extinf']}\n")
                        f.write(f"{channel['url']}\n\n")

            print(f"💾 对比结果已保存到: {output_file}")
        except Exception as e:
            print(f"❌ 保存结果文件时出错: {str(e)}")

    def _get_current_time(self):
        """获取当前时间字符串"""
        from datetime import datetime
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def main():
    parser = argparse.ArgumentParser(
        description='M3U文件对比工具 - 找出只在一个文件中存在的URL',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
使用示例:
  python3 m3u_comparator.py file1.m3u file2.m3u
  python3 m3u_comparator.py file1.m3u file2.m3u --output diff_result.txt
        '''
    )

    parser.add_argument('file1', help='第一个M3U文件路径',default="iptvscanner.m3u")
    parser.add_argument('file2', help='第二个M3U文件路径',default='四川联通.m3u')
    parser.add_argument('--output', '-o', help='输出结果文件路径',default="diff_result.txt")

    args = parser.parse_args()

    comparator = M3UComparator()

    try:
        results = comparator.compare_files(
            args.file1,
            args.file2,
            args.output
        )

        print("\n🎉 对比完成!")

    except Exception as e:
        print(f"💥 对比过程中发生错误: {str(e)}")


if __name__ == "__main__":
    main()