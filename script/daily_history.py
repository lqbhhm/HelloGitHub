#!/usr/bin/env python
# -*- coding:utf-8 -*-
import os
import sys
import subprocess

STATE_FILE = '.github/history_state'
CONTENT_DIR = 'content'

def read_state():
    if not os.path.exists(STATE_FILE):
        return 1
    with open(STATE_FILE, 'r') as f:
        try:
            return int(f.read().strip())
        except ValueError:
            return 1

def write_state(num):
    # Ensure directory exists
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        f.write(str(num))

def get_content_file(num):
    # Try different padding formats
    # 1 -> HelloGitHub01.md
    # 10 -> HelloGitHub10.md
    
    # Try 2-digit padding first (most common for early issues)
    filename_padded = 'HelloGitHub{:02d}.md'.format(num)
    path_padded = os.path.join(CONTENT_DIR, filename_padded)
    
    # Try no padding (if any exists, though early ones seem to be padded)
    filename_normal = 'HelloGitHub{}.md'.format(num)
    path_normal = os.path.join(CONTENT_DIR, filename_normal)
    
    if os.path.exists(path_padded):
        return path_padded
    elif os.path.exists(path_normal):
        return path_normal
    else:
        return None

def main():
    current_num = read_state()
    print("Current history issue number: {}".format(current_num))
    
    file_path = get_content_file(current_num)
    
    if not file_path:
        print("Content file for issue {} not found. Stopping history push.".format(current_num))
        # Maybe we reached the end? Or a gap?
        # Let's verify if a higher number exists to be sure, but for now just exit.
        return

    print("Found file: {}".format(file_path))
    
    # Call the notification script
    # We assume notify_feishu.py is in script/notify_feishu.py
    # and we are running from root
    notify_script = os.path.join('script', 'notify_feishu.py')
    
    if not os.path.exists(notify_script):
        print("Error: notify script not found at {}".format(notify_script))
        sys.exit(1)
        
    print("Sending notification for issue {}...".format(current_num))
    try:
        # Pass environment variables to the subprocess
        env = os.environ.copy()
        subprocess.check_call([sys.executable, notify_script, file_path], env=env)
        print("Notification sent successfully.")
        
        # Increment and save state
        next_num = current_num + 1
        write_state(next_num)
        print("State updated to {}".format(next_num))
        
    except subprocess.CalledProcessError as e:
        print("Error sending notification: {}".format(e))
        sys.exit(1)

if __name__ == '__main__':
    main()
