#!/usr/bin/env python
# -*- coding:utf-8 -*-
import os
import sys
import re
import json
import requests

def get_issue_number(content):
    match = re.search(r'# 《HelloGitHub》第 (\d+) 期', content)
    if match:
        return match.group(1)
    return None

def send_feishu_card(title, issue_num):
    webhook_url = os.environ.get('FEISHU_WEBHOOK_URL')
    if not webhook_url:
        print("Error: FEISHU_WEBHOOK_URL environment variable not set.")
        return False

    online_url = "https://hellogithub.com/periodical/volume/{}/".format(issue_num)
    
    card = {
        "schema": "2.0",
        "header": {
            "template": "blue",
            "title": {
                "tag": "plain_text",
                "content": title
            }
        },
        "body": {
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**HelloGitHub 第 {} 期已发布！**\n点击下方按钮在线阅读全文。".format(issue_num)
                    }
                },
                {
                    "tag": "button",
                    "text": {
                        "tag": "plain_text",
                        "content": "在线阅读全文"
                    },
                    "type": "primary",
                    "multi_url": {
                        "url": online_url,
                        "pc_url": "",
                        "android_url": "",
                        "ios_url": ""
                    }
                }
            ]
        }
    }

    data = {
        "msg_type": "interactive",
        "card": card
    }

    try:
        response = requests.post(webhook_url, json=data)
        response.raise_for_status()
        result = response.json()
        if result.get("code") == 0:
            print("Successfully sent card: {}".format(title))
            return True
        else:
            print("Failed to send card {}: {}".format(title, result))
            return False
    except Exception as e:
        print("Error sending request for {}: {}".format(title, e))
        return False

def main():
    if len(sys.argv) < 2:
        print("Usage: python notify_feishu.py <markdown_file_path>")
        sys.exit(1)

    file_path = sys.argv[1]
    if not os.path.exists(file_path):
        print("File not found: {}".format(file_path))
        sys.exit(1)

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    issue_num = get_issue_number(content)
    if not issue_num:
        basename = os.path.basename(file_path)
        match = re.search(r'HelloGitHub(\d+).md', basename)
        if match:
            issue_num = match.group(1)
        else:
            issue_num = "Update"

    title = "HelloGitHub 第 {} 期".format(issue_num)
    send_feishu_card(title, issue_num)

if __name__ == '__main__':
    main()
