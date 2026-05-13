#!/bin/bash
pkill pure-ftpd
rm -rf /home/fuzzing/*

TARGET_DIR="/home/ubuntu"  # 要清理的目录（绝对路径/相对路径）
KEEP_NAMES=("experiments" "voltron") # 要保留的文件夹名称（多个用空格分隔）

for item in "$TARGET_DIR"/*; do

    if [ -d "$item" ]; then
        folder_name=$(basename "$item")
        if ! [[ " ${KEEP_NAMES[@]} " =~ " $folder_name " ]]; then
            rm -rf "$item"
            rm -f "$item"
        fi
    fi
done