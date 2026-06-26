
scan:
	python extract_table_scan.py ../plan_info.csv > table_scan_rows.csv

get_single_op_execution_time:
	awk 'BEGIN{FS=OFS=";"} NR==1{print; next} { $$8 = sprintf("%.6f", $$8/$$5); print }' ../plan_info.csv > single_op_execution_time.csv