#!/bin/bash

folder=$1   #gcovr result folder
covfile=$2  #path to coverage file

#process fuzzer-generated testcases
cov_data=$(gcovr -r $folder -s | grep "[lb][a-z]*:")
l_per=$(echo "$cov_data" | grep lines | cut -d" " -f2 | rev | cut -c2- | rev)
l_abs=$(echo "$cov_data" | grep lines | cut -d" " -f3 | cut -c2-)
b_per=$(echo "$cov_data" | grep branch | cut -d" " -f2 | rev | cut -c2- | rev)
b_abs=$(echo "$cov_data" | grep branch | cut -d" " -f3 | cut -c2-)

echo "$time,$l_per,$l_abs,$b_per,$b_abs" >> $covfile