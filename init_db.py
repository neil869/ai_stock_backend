#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
初始化数据库表结构
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import create_tables

def main():
    """主函数"""
    try:
        create_tables()
        print("数据库表结构初始化成功")
    except Exception as e:
        print(f"数据库表结构初始化失败: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
