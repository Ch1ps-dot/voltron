#!/bin/bash

folder=$1   #gcovr result folder
covfile=$2  #path to coverage file
file=$3 #conversation file

#process fuzzer-generated testcases
time=$(stat -c %Y $file)
cp /home/fuzzing/home/ubuntu/experiments/pure-ftpd-gcov/src/*.gcda /home/ubuntu/experiments/pure-ftpd-gcov/src/ > /dev/null 2>&1
cov_data=$(gcovr -r /home/ubuntu/experiments/pure-ftpd-gcov -s | grep "[lb][a-z]*:")
l_per=$(echo "$cov_data" | grep lines | cut -d" " -f2 | rev | cut -c2- | rev)
l_abs=$(echo "$cov_data" | grep lines | cut -d" " -f3 | cut -c2-)
b_per=$(echo "$cov_data" | grep branch | cut -d" " -f2 | rev | cut -c2- | rev)
b_abs=$(echo "$cov_data" | grep branch | cut -d" " -f3 | cut -c2-)

echo "$time,$l_per,$l_abs,$b_per,$b_abs" >> $covfile