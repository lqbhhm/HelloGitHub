#!/usr/bin/env python
# -*- coding:utf-8 -*-
import os
import sys
import re
import time
import json
import mimetypes
import requests
from requests_toolbelt import MultipartEncoder

def get_issue_number(content):
    match = re.search(r'# 《HelloGitHub》第 (\d+) 期', content)
    if match:
        return match.group(1)
    return None

def get_tenant_access_token(app_id, app_secret):
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    headers = {"Content-Type": "application/json; charset=utf-8"}
    item_data = {
        "app_id": app_id,
        "app_secret": app_secret
    }
    try:
        response = requests.post(url, headers=headers, json=item_data)
        response.raise_for_status()
        return response.json().get("tenant_access_token")
    except Exception as e:
        print("Error getting access token: {}".format(e))
        return None

def upload_image(image_url, access_token):
    try:
        # Download image
        img_resp = requests.get(image_url)
        img_resp.raise_for_status()
        content = img_resp.content
        
        content_type = img_resp.headers.get('Content-Type')
        if not content_type:
            content_type, _ = mimetypes.guess_type(image_url)
        
        if not content_type:
            content_type = 'image/jpeg' # Fallback
            
        ext = mimetypes.guess_extension(content_type) or '.jpg'
        filename = 'image{}'.format(ext)

        # Upload to Feishu
        url = "https://open.feishu.cn/open-apis/im/v1/images"
        form = {'image_type': 'message',
                'image': (filename, content, content_type)}
        multi_encoder = MultipartEncoder(form)
        headers = {
            'Authorization': 'Bearer {}'.format(access_token),
            'Content-Type': multi_encoder.content_type
        }
        
        response = requests.post(url, headers=headers, data=multi_encoder)
        
        if response.status_code == 200:
            result = response.json()
            if result.get("code") == 0:
                return result.get("data", {}).get("image_key")
            else:
                print("Failed to upload image {}: {}".format(image_url, result))
                return None
        else:
            print("HTTP {} Error uploading image {}: {}".format(response.status_code, image_url, response.text))
            return None
    except Exception as e:
        print("Exception uploading image {}: {}".format(image_url, e))
        return None

def parse_markdown(content):
    lines = content.split('\n')
    categories = []
    current_category = None
    
    # Regex for project items
    item_pattern = re.compile(r'^\d+、\[(.*?)\]\((.*?)\)(?:：|:)(.*)')
    # Regex for images
    img_html_pattern = re.compile(r"<img[^>]*src=['\"](.*?)['\"][^>]*>")
    img_md_pattern = re.compile(r"!\[.*?\]\((.*?)\)")
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Stop parsing if we hit a Level 2 header (e.g. ## 赞助, ## 声明) after we have started collecting sections
        if line.startswith('## '):
             if current_category:
                 categories.append(current_category)
                 current_category = None
             continue
            
        if line.startswith('### '):
            if current_category:
                categories.append(current_category)
            category_title = line.replace('###', '').strip()
            current_category = {'title': category_title, 'items': []}
        
        elif current_category is not None:
            # Check for project item
            match = item_pattern.match(line)
            if match:
                name, url, desc = match.groups()
                current_category['items'].append({
                    'type': 'project',
                    'name': name.strip(),
                    'url': url.strip(),
                    'desc': desc.strip()
                })
                continue
            
            # Check for images
            img_match = img_html_pattern.search(line)
            if not img_match:
                img_match = img_md_pattern.search(line)
            
            if img_match:
                img_url = img_match.group(1)
                
                # Filter out unwanted images (logos, license buttons, etc.)
                if 'img_logo' in img_url or 'licensebuttons.net' in img_url:
                    continue
                    
                current_category['items'].append({
                    'type': 'image',
                    'url': img_url
                })

    if current_category:
        categories.append(current_category)
        
    return categories

def send_feishu_card(title, elements):
    webhook_url = os.environ.get('FEISHU_WEBHOOK_URL')
    if not webhook_url:
        print("Error: FEISHU_WEBHOOK_URL environment variable not set.")
        return False

    card = {
        "header": {
            "template": "blue",
            "title": {
                "tag": "plain_text",
                "content": title
            }
        },
        "elements": elements
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

    # Get credentials
    app_id = os.environ.get('FEISHU_APP_ID')
    app_secret = os.environ.get('FEISHU_APP_SECRET')
    access_token = None
    
    if app_id and app_secret:
        print("App ID/Secret found, attempting to get access token for image upload...")
        access_token = get_tenant_access_token(app_id, app_secret)
        if access_token:
            print("Access token obtained.")

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

    categories = parse_markdown(content)
    
    if not categories:
        print("No categories found to notify.")
        return

    # 1. Send Intro Card
    intro_title = "HelloGitHub 第 {} 期发布".format(issue_num)
    intro_elements = []
    
    # Try to find a cover image in the first category (usually "Preface" or "Other") or use a default one ?
    # Let's verify if there is any image in proper categories, or check if 'HelloGitHub' logo is available.
    # For now, just a text summary.
    intro_elements.append({
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": "**本期内容如下：**"
        }
    })
    
    # Add a main button to read online
    online_url = "https://hellogithub.com/periodical/volume/{}/".format(issue_num)
    intro_elements.append({
        "tag": "action",
        "actions": [{
            "tag": "button",
            "text": {
                "tag": "plain_text",
                "content": "在线阅读全文"
            },
            "type": "primary",
            "url": online_url
        }]
    })

    send_feishu_card(intro_title, intro_elements)
    
    # 2. Send Category Cards
    for cat in categories:
        cat_title = "HG Vol.{} - {}".format(issue_num, cat['title'])
        cat_elements = []
        
        for item in cat['items']:
            if item['type'] == 'project':
                # Format: **[Name](Url)** \n Description
                md_text = "**[{}]({})**\n{}".format(item['name'], item['url'], item['desc'])
                cat_elements.append({
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": md_text
                    }
                })
                # Add a divider after each project for cleanliness? Or maybe just spacing.
                # A divider might be too much if there are many projects. Let's stick to spacing (div block implies new line).
                
            elif item['type'] == 'image' and access_token:
                # Upload and display image
                print("Uploading image: {}".format(item['url']))
                image_key = upload_image(item['url'], access_token)
                if image_key:
                    cat_elements.append({
                        "tag": "img",
                        "img_key": image_key,
                        "alt": {
                            "tag": "plain_text",
                            "content": "Project Image"
                        }
                    })
        
        if cat_elements:
            # If too many elements, Feishu might complain (50 element limit?)
            # Usually HG categories are okay size.
            send_feishu_card(cat_title, cat_elements)
            time.sleep(1)

if __name__ == '__main__':
    main()
