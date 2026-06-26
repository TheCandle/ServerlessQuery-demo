validate_tb_pdg:
	python scripts/validate_tb_pdg.py \
            --plan_csv ./data_kunpeng/tpch_output_22/plan_info.csv \
            --query_id 5 \
            --query_dop 64 \
            --no_dop_model_dir  ./output/tpch/models/exact_train/operator_non_dop_aware \
            --dop_model_dir ./output/tpch/models/exact_train/operator_dop_aware \
            --output_json output/validation_q5_d64.json \
            --output_txt output/validation_q5_d64.txt --verbose
