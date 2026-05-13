#!/bin/bash

folder=$1   #gcovr result folder
covfile=$2  #path to coverage file

#delete the existing coverage file
rm $covfile; touch $covfile

#clear gcov data
#since the source files of LightFTP are stored in the parent folder of the current folder
gcovr -r $folder -s -d > /dev/null 2>&1

#output the header of the coverage file which is in the CSV format
#Time: timestamp, l_per/b_per and l_abs/b_abs: line/branch coverage in percentage and absolutate number
echo "Time,l_per,l_abs,b_per,b_abs" >> $covfile


