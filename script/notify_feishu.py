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
        img_resp = requests.get(image_url) # Not streaming
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
        # response.raise_for_status() # Don't raise yet, check response first
        
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
    """
    Parses the markdown content into a structured format.
    Returns a list of categories, where each category has a title and a list of items.
    Structure: [{'title': 'C 项目', 'items': [{'type': 'project', 'name': '...', 'url': '...', 'desc': '...'}, {'type': 'image', 'url': '...'}]}]
    """
    lines = content.split('\n')
    categories = []
    current_category = None
    
    # Regex for project items
    item_pattern = re.compile(r'^\d+、\[(.*?)\]\((.*?)\)(?:：|:)(.*)')
    # Regex for images: <img src='url'> or ![](url)
    img_html_pattern = re.compile(r"<img[^>]*src=['\"](.*?)['\"][^>]*>")
    img_md_pattern = re.compile(r"!\[.*?\]\((.*?)\)")
    
    for line in lines:
        line = line.strip()
        if not line:
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
                # Filter out small icons or badges if possible, but for now take all
                current_category['items'].append({
                    'type': 'image',
                    'url': img_url
                })

    if current_category:
        categories.append(current_category)
        
    return categories

def send_feishu_msg(title, content_lines):
    webhook_url = os.environ.get('FEISHU_WEBHOOK_URL')
    if not webhook_url:
        print("Error: FEISHU_WEBHOOK_URL environment variable not set.")
        return False

    post_content = []
    
    for line_data in content_lines:
        if line_data['type'] == 'text':
             post_content.append([{
                 'tag': 'text',
                 'text': line_data['text']
             }])
        elif line_data['type'] == 'link_item':
            post_content.append([
                {
                    'tag': 'text',
                    'text': "• "
                },
                {
                    'tag': 'a',
                    'text': line_data['name'],
                    'href': line_data['url']
                },
                {
                    'tag': 'text',
                    'text': "：{}".format(line_data['desc'])
                }
            ])
        elif line_data['type'] == 'image':
             post_content.append([{
                 'tag': 'img',
                 'image_key': line_data['image_key']
             }])

    data = {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": title,
                    "content": post_content
                }
            }
        }
    }

    try:
        response = requests.post(webhook_url, json=data)
        response.raise_for_status()
        result = response.json()
        if result.get("code") == 0:
            print("Successfully sent chunk: {}".format(title))
            return True
        else:
            print("Failed to send chunk {}: {}".format(title, result))
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
        else:
            print("Failed to get access token, images will be skipped.")
    else:
        print("FEISHU_APP_ID or FEISHU_APP_SECRET not set. Images will be skipped.")

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

    # Intro
    intro_title = "HelloGitHub 第 {} 期发布".format(issue_num)
    intro_lines = [{'type': 'text', 'text': "本期内容如下："}]
    send_feishu_msg(intro_title, intro_lines)
    
    for cat in categories:
        cat_title = "HG Vol.{} - {}".format(issue_num, cat['title'])
        cat_lines = []
        for item in cat['items']:
            if item['type'] == 'project':
                cat_lines.append({
                    'type': 'link_item',
                    'name': item['name'],
                    'url': item['url'],
                    'desc': item['desc']
                })
            elif item['type'] == 'image' and access_token:
                # Upload image
                print("Uploading image: {}".format(item['url']))
                image_key = upload_image(item['url'], access_token)
                if image_key:
                    cat_lines.append({
                        'type': 'image',
                        'image_key': image_key
                    })
        
        if cat_lines:
            send_feishu_msg(cat_title, cat_lines)
            time.sleep(1)

if __name__ == '__main__':
    main()
