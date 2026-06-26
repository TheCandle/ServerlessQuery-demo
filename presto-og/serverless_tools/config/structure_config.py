from math import sqrt

# 导入系统配置
from .main_config import USE_HASH_TABLE_SIZE_FEATURE, DEFAULT_DOP, THREAD_COST, THREAD_MEM

# Create lowercase aliases for compatibility with existing code
default_dop = DEFAULT_DOP
thread_cost = THREAD_COST
thread_mem = THREAD_MEM

# 1. 定义列类型到开销的映射
column_type_cost_dict = {
    'INT': 4,              # INT 类型开销 4 字节
    'BIGINT': 8,           # BIGINT 类型开销 8 字节
    'CHAR': lambda s: 4 + s * 2,   # CHAR(n) 类型开销为 n 字节
    'VARCHAR': lambda s: 4 + s * 2, # VARCHAR(n) 类型开销为 n 字节
    'DECIMAL': lambda p, s: 4 + 4 + (p + s),  # DECIMAL(p, s) 假设开销为 (p + s) / 2 字节
    'DATE': 8              # DATE 类型开销 8 字节
}

tpcds_non_parallel = {1,2,3,9,23,24,30,32,33,42,54,56,57,59,60,63,64,77,80,81,92}

# 2. 预定义的表结构及列类型
table_structure = {
    'REGION': [
        ('R_REGIONKEY', 'INT'),
        ('R_NAME', 'CHAR(25)'),
        ('R_COMMENT', 'VARCHAR(152)')
    ],
    'NATION': [
        ('N_NATIONKEY', 'INT'),
        ('N_NAME', 'CHAR(25)'),
        ('N_REGIONKEY', 'INT'),
        ('N_COMMENT', 'VARCHAR(152)')
    ],
    'SUPPLIER': [
        ('S_SUPPKEY', 'BIGINT'),
        ('S_NAME', 'CHAR(25)'),
        ('S_ADDRESS', 'VARCHAR(40)'),
        ('S_NATIONKEY', 'INT'),
        ('S_PHONE', 'CHAR(15)'),
        ('S_ACCTBAL', 'DECIMAL(15,2)'),
        ('S_COMMENT', 'VARCHAR(101)')
    ],
    'CUSTOMER': [
        ('C_CUSTKEY', 'BIGINT'),
        ('C_NAME', 'VARCHAR(25)'),
        ('C_ADDRESS', 'VARCHAR(40)'),
        ('C_NATIONKEY', 'INT'),
        ('C_PHONE', 'CHAR(15)'),
        ('C_ACCTBAL', 'DECIMAL(15,2)'),
        ('C_MKTSEGMENT', 'CHAR(10)'),
        ('C_COMMENT', 'VARCHAR(117)')
    ],
    'PART': [
        ('P_PARTKEY', 'BIGINT'),
        ('P_NAME', 'VARCHAR(100)'),
        ('P_MFGR', 'CHAR(100)'),
        ('P_BRAND', 'CHAR(20)'),
        ('P_TYPE', 'VARCHAR(100)'),
        ('P_SIZE', 'BIGINT'),
        ('P_CONTAINER', 'CHAR(10)'),
        ('P_RETAILPRICE', 'DECIMAL(15,2)'),
        ('P_COMMENT', 'VARCHAR(23)')
    ],
    'PARTSUPP': [
        ('PS_PARTKEY', 'BIGINT'),
        ('PS_SUPPKEY', 'BIGINT'),
        ('PS_AVAILQTY', 'BIGINT'),
        ('PS_SUPPLYCOST', 'DECIMAL(15,2)'),
        ('PS_COMMENT', 'VARCHAR(199)')
    ],
    'ORDERS': [
        ('O_ORDERKEY', 'BIGINT'),
        ('O_CUSTKEY', 'BIGINT'),
        ('O_ORDERSTATUS', 'CHAR(1)'),
        ('O_TOTALPRICE', 'DECIMAL(15,2)'),
        ('O_ORDERDATE', 'DATE'),
        ('O_ORDERPRIORITY', 'CHAR(15)'),
        ('O_CLERK', 'CHAR(15)'),
        ('O_SHIPPRIORITY', 'BIGINT'),
        ('O_COMMENT', 'VARCHAR(79)')
    ],
    'LINEITEM': [
        ('L_ORDERKEY', 'BIGINT'),
        ('L_PARTKEY', 'BIGINT'),
        ('L_SUPPKEY', 'BIGINT'),
        ('L_LINENUMBER', 'BIGINT'),
        ('L_QUANTITY', 'DECIMAL(15,2)'),
        ('L_EXTENDEDPRICE', 'DECIMAL(15,2)'),
        ('L_DISCOUNT', 'DECIMAL(15,2)'),
        ('L_TAX', 'DECIMAL(15,2)'),
        ('L_RETURNFLAG', 'CHAR(1)'),
        ('L_LINESTATUS', 'CHAR(1)'),
        ('L_SHIPDATE', 'DATE'),
        ('L_COMMITDATE', 'DATE'),
        ('L_RECEIPTDATE', 'DATE'),
        ('L_SHIPINSTRUCT', 'CHAR(25)'),
        ('L_SHIPMODE', 'CHAR(10)'),
        ('L_COMMENT', 'VARCHAR(44)')
    ]
}

# OPERATORS_WITHOUT_FEATURES = {
#     'Row Adapter', 'Vector Limit', 'Vector Sort Aggregate',
#     'Vector Subquery Scan', 'Sort', 'Nested Loop',
#     # 根据你的实际情况添加或删除
# }

# 假设已知的 jointype 和 table_names 类型
jointypes = ['none', 'Inner', 'Right', 'Left', 'Full', 'Semi', 'Anti', 'Right Semi', 'Right Anti', 'Left Anti Full', 'Right Anti Full']
table_names = ['none', 'region', 'nation', 'supplier', 'customer', 'part', 'partsupp', 'orders', 'lineitem']
operator_type =[
    'CStore Index Scan',
        'Vector Nest Loop',
        'Vector Merge Join',
        'Aggregate',
        'Hash',
        'Vector WindowAgg',
        'Append',
        'Index Only Scan',
        'Hash Join',
        'CStore Scan',
        'Vector Materialize',
        'Vector Aggregate',
        'Vector Sort',
        'Vector Hash Aggregate',
        'Vector Sonic Hash Aggregate',
        'Vector Hash Join',
        'Vector Sonic Hash Join',
        'Vector Streaming LOCAL GATHER',
        'Vector Streaming LOCAL REDISTRIBUTE', 
        'Vector Streaming BROADCAST',
        'Vector SetOp',
        'Vector Append',
        'Row Adapter',
        'Vector Limit',
        'Streaming(type: BROADCAST dop: 64/1)',
        'Streaming(type: LOCAL REDISTRIBUTE dop: 64/64)', 
        'Streaming(type: LOCAL GATHER dop: 1/64)',
        'Vector Subquery Scan',
        'CTE Scan',


        # presto算子
         'ScanFilterProject',
        'Aggregate',
        'AssignUniqueId',
        'CrossJoin',
        'EnforceSingleRow',
        'FilterProject',
        'InnerJoin',
        'LeftJoin',
        'LocalExchange',
        'LocalMerge',
        'PartialSort',
        'Project',
        'RemoteSource',
        'ScanFilter',
        'ScanProject',
        'SemiJoin',
        'TableScan',
        ]
# 创建编码字典
jointype_encoding = {jointype: idx for idx, jointype in enumerate(jointypes)}
table_names_encoding = {table_name: idx for idx, table_name in enumerate(table_names)}
operator_encoding = {operator_type: idx for idx, operator_type in enumerate(operator_type)}

# Materialized (pipeline breaker) operator rules.
# Keep this centralized so switching engine/operator names only needs config changes.
materialized_operator_types = {
    # openGauss / legacy
    'Vector Materialize',
    'Vector Aggregate',
    'Vector Hash Aggregate',
    'Vector Sonic Hash Aggregate',
    'Vector Sort',
    'Vector Sort Aggregate',
    'Vector Streaming LOCAL GATHER',
    'Vector Streaming LOCAL REDISTRIBUTE',
    'Vector Streaming BROADCAST',
    'Streaming(type: BROADCAST dop: 64/1)',
    'Streaming(type: LOCAL REDISTRIBUTE dop: 64/64)',
    'Streaming(type: LOCAL GATHER dop: 1/64)',
    'Hash',
    'Hash Join',
    'Aggregate',
    # Presto
    # 'LocalExchange',
    # 'LocalMerge',
    # 'PartialSort',
    # 'RemoteSource',
    # 'EnforceSingleRow',
    # 'lookupjoinoperator',
    'HashBuilderOperator'
}

# Keyword fallback for engines/operators not explicitly listed above.
materialized_operator_keywords = (
    'materialize',
    'aggregate',
    'sort',
    # 'hash',
    # 'exchange',
    # 'join',
    # 'remote',
    # 'merge',
    # 'enforcesinglerow',
)

parallel_op = [
        'CStore Scan',
        'Vector Materialize',
        'Vector Aggregate',
        'Vector Sort',
        'Vector Hash Aggregate',
        'Vector Sonic Hash Aggregate',
        'Vector Hash Join',
        'Vector Sonic Hash Join',
        'Vector Streaming LOCAL GATHER',
        'Vector Streaming LOCAL REDISTRIBUTE', 
        'Vector Streaming BROADCAST',
        'Streaming(type: BROADCAST dop: 64/1)',
        'Streaming(type: LOCAL REDISTRIBUTE dop: 64/64)', 
        'Streaming(type: LOCAL GATHER dop: 1/64)',
        'Vector Result',
        'Vector WindowAgg',
        'Vector SetOp',
        'Vector Append',
        'Vector Limit',
        'Vector Subquery Scan',
        'Vector Sort Aggregate',
        'Aggregate',
        'Hash',
        'Hash Join',
        'Row Adapter',


        # presto
        'ScanFilterProject',
        'Aggregate',
        'AssignUniqueId',
        'CrossJoin',
        'EnforceSingleRow',
        'FilterProject',
        'InnerJoin',
        'LeftJoin',
        'LocalExchange',
        'LocalMerge',
        'PartialSort',
        'Project',
        'RemoteSource',
        'ScanFilter',
        'ScanProject',
        'SemiJoin',
        'TableScan',
]

# 训练时一个个那该列表中算子的特征进行训练
operator_lists = [
        'CStore Index Scan',
        'Vector Nest Loop',
        'Vector Merge Join',
        'Aggregate',
        'Hash',
        'Vector WindowAgg',
        'Append',
        'Index Only Scan',
        'Hash Join',
        'CStore Scan',
        'Vector Materialize',
        'Vector Aggregate',
        'Vector Sort',
        'Vector Hash Aggregate',
        'Vector Sonic Hash Aggregate',
        'Vector Hash Join',
        'Vector Sonic Hash Join',
        'Vector Streaming LOCAL GATHER',
        'Vector Streaming LOCAL REDISTRIBUTE', 
        'Vector Streaming BROADCAST',
        'Vector SetOp',
        'Vector Append',

        # presto算子
        'ScanFilterProject',
        'Aggregate',
        'AssignUniqueId',
        'CrossJoin',
        'EnforceSingleRow',
        'FilterProject',
        'InnerJoin',
        'LeftJoin',
        'LocalExchange',
        'LocalMerge',
        'PartialSort',
        'Project',
        'RemoteSource',
        'ScanFilter',
        'ScanProject',
        'SemiJoin',
        'TableScan',
]
no_dop_operators_exec = [
        'CStore Index Scan',
        'Vector Nest Loop',
        'Vector WindowAgg',
        'Index Only Scan',
        'Vector Merge Join',
]

dop_operators_exec = [
        # 'CStore Scan',
        # 'Vector Materialize',
        # 'Vector Aggregate',
        # 'Vector Sort',
        # 'Vector Hash Aggregate',
        # 'Vector Sonic Hash Aggregate',
        # 'Vector Hash Join',
        # 'Vector Sonic Hash Join',
        # 'Vector Streaming LOCAL GATHER',
        # 'Vector Streaming LOCAL REDISTRIBUTE', 
        # 'Vector Streaming BROADCAST',
        # 'Vector SetOp',
        # 'Vector Append',
        # 'Aggregate',
        # 'Hash',
        # 'Append',
        # 'Hash Join',


        # Presto
        'ScanFilterProject',
        'Aggregate',
        'AssignUniqueId',
        'CrossJoin',
        'EnforceSingleRow',
        'FilterProject',
        'InnerJoin',
        'LeftJoin',
        'LocalExchange',
        'LocalMerge',
        'PartialSort',
        'Project',
        'RemoteSource',
        'ScanFilter',
        'ScanProject',
        'SemiJoin',
        'TableScan',
        
]

no_dop_operators_mem = [
    'Vector Materialize',
    'Vector Aggregate',
    'Vector Sort',
    'Vector Hash Aggregate',
    'Vector Sonic Hash Aggregate',
    'Vector Hash Join',
    'Vector Sonic Hash Join',
    'Vector WindowAgg',
    'Aggregate',
    'Hash',
]

dop_operators_mem = [
        # 'Vector Materialize',
        # 'Vector Aggregate',
        # 'Vector Sort',
        # 'Vector Hash Aggregate',
        # 'Vector Sonic Hash Aggregate',
        # 'Vector Hash Join',
        # 'Vector Sonic Hash Join',
        # 'Vector SetOp',

        'ScanFilterProject',
        'Aggregate',
        'AssignUniqueId',
        'CrossJoin',
        'EnforceSingleRow',
        'FilterProject',
        'InnerJoin',
        'LeftJoin',
        'LocalExchange',
        'LocalMerge',
        'PartialSort',
        'Project',
        'RemoteSource',
        'ScanFilter',
        'ScanProject',
        'SemiJoin',
        'TableScan',
]


no_dop_operator_features = {
    'CStore Index Scan': {
        'exec': ['l_input_rows', 'actual_rows', 'width', 'index_cost', 'predicate_cost'],
        'mem': ['l_input_rows', 'actual_rows', 'width', 'query_dop']
    },
    'CTE Scan': {
        'exec': ['l_input_rows', 'actual_rows', 'width', 'predicate_cost'],
        'mem': ['l_input_rows', 'actual_rows', 'width']
    },
    # Add mappings for other operators here
    'Vector Nest Loop': {
        'exec': ['l_input_rows', 'r_input_rows', 'actual_rows', 'width', 'jointype', 'query_dop'],
        'mem': ['l_input_rows', 'r_input_rows', 'actual_rows', 'width', 'jointype', 'query_dop']
    },
    'Vector Merge Join': {
        'exec': ['l_input_rows', 'r_input_rows', 'actual_rows', 'width', 'jointype'],
        'mem': ['l_input_rows', 'r_input_rows', 'actual_rows', 'width','jointype']
    },
    'Vector WindowAgg': {
        'exec': ['l_input_rows', 'actual_rows', 'width'],
        'mem': ['l_input_rows', 'actual_rows', 'width']
    },
    'Index Only Scan': {
        'exec': ['l_input_rows', 'actual_rows', 'width', 'index_cost', 'predicate_cost'],
        'mem': ['l_input_rows', 'actual_rows', 'width']
    },
    'Vector Aggregate': {
        'exec': ['l_input_rows', 'actual_rows', 'width', 'agg_width'],
        'mem': ['l_input_rows', 'actual_rows', 'width', 'agg_width']
    },
    'Vector Sort': {
        'exec': ['l_input_rows', 'actual_rows', 'width'],
        'mem': ['l_input_rows', 'actual_rows', 'width']
    },
    'Vector Materialize': {
        'exec': ['l_input_rows', 'actual_rows', 'width'],
        'mem': ['l_input_rows', 'actual_rows', 'width']
    },
    'Vector Hash Aggregate': {
        'exec': ['l_input_rows', 'width', 'agg_col', 'agg_width', 'hash_table_size', 'disk_ratio'],
        'mem': ['actual_rows', 'width', 'agg_col', 'agg_width', 'hash_table_size', 'disk_ratio']
    },
    # 'Vector Hash Aggregate': {
    #     'exec': ['l_input_rows', 'width', 'agg_col', 'agg_width', 'disk_ratio'] + (['hash_table_size'] if USE_HASH_TABLE_SIZE_FEATURE else []),
    #     'mem': ['actual_rows', 'width', 'agg_col', 'agg_width', 'disk_ratio'] + (['hash_table_size'] if USE_HASH_TABLE_SIZE_FEATURE else [])
    # },
    'Vector Sonic Hash Aggregate': {
        'exec': ['l_input_rows', 'width', 'agg_col', 'agg_width', 'hash_table_size', 'disk_ratio'],
        'mem': ['actual_rows', 'width', 'agg_col', 'agg_width', 'hash_table_size', 'disk_ratio']
    },
    # 'Vector Sonic Hash Aggregate': {
    #     'exec': ['l_input_rows', 'width', 'agg_col', 'agg_width', 'disk_ratio'] + (['hash_table_size'] if USE_HASH_TABLE_SIZE_FEATURE else []),
    #     'mem': ['actual_rows', 'width', 'agg_col', 'agg_width', 'disk_ratio'] + (['hash_table_size'] if USE_HASH_TABLE_SIZE_FEATURE else [])
    # },
    'Vector Hash Join': {
        'exec': ['l_input_rows', 'r_input_rows',  'width', 'jointype', 'predicate_cost', 'hash_table_size'],
        'mem': ['r_input_rows', 'width', 'hash_table_size']
    },
    'Vector Sonic Hash Join': {
        'exec': ['l_input_rows', 'r_input_rows',  'width', 'jointype', 'predicate_cost','hash_table_size'],
        'mem': ['r_input_rows', 'width', 'hash_table_size']
    },
    # 'Vector Hash Join': {
    #     'exec': ['l_input_rows', 'r_input_rows', 'width', 'jointype', 'predicate_cost'] + (['hash_table_size'] if USE_HASH_TABLE_SIZE_FEATURE else []),
    #     'mem': ['r_input_rows', 'width'] + (['hash_table_size'] if USE_HASH_TABLE_SIZE_FEATURE else [])
    # },
    # 'Vector Sonic Hash Join': {
    #     'exec': ['l_input_rows', 'r_input_rows', 'width', 'jointype', 'predicate_cost'] + (['hash_table_size'] if USE_HASH_TABLE_SIZE_FEATURE else []),
    #     'mem': ['r_input_rows', 'width'] + (['hash_table_size'] if USE_HASH_TABLE_SIZE_FEATURE else [])
    # },
    'Vector SetOp': {
        'exec': ['l_input_rows',  'actual_rows', 'width'],
        'mem': ['l_input_rows', 'actual_rows', 'width']
    },
    'Aggregate': {
        'exec': ['l_input_rows', 'width', 'agg_col', 'agg_width'],
        'mem': ['l_input_rows', 'width', 'agg_col', 'agg_width']
    },
    'Vector Sort Aggregate': {
        'exec': ['l_input_rows', 'width', 'agg_col', 'agg_width'],
        'mem': ['l_input_rows', 'width', 'agg_col', 'agg_width']
    },
    'Hash Join': {
        'exec': ['l_input_rows', 'r_input_rows', 'actual_rows', 'width', 'jointype', 'predicate_cost', 'hash_table_size'],
        'mem': ['r_input_rows', 'width', 'jointype', 'hash_table_size']
    },
    # 'Hash Join': {
    #     'exec': ['l_input_rows', 'r_input_rows', 'actual_rows', 'width', 'jointype', 'predicate_cost'] + (['hash_table_size'] if USE_HASH_TABLE_SIZE_FEATURE else []),
    #     'mem': ['r_input_rows', 'width', 'jointype'] + (['hash_table_size'] if USE_HASH_TABLE_SIZE_FEATURE else [])
    # },
    'Hash': {
        'exec': ['l_input_rows', 'actual_rows', 'width'],
        'mem': ['l_input_rows', 'actual_rows', 'width']
    },
    'Append': {
        'exec': ['l_input_rows', 'actual_rows', 'width'],
        'mem': ['l_input_rows', 'actual_rows', 'width']
    },
    # Add more operators and their corresponding feature sets here as needed
}

# 这里定义每个算子训练时用到的特征
dop_operator_features = {
    # 'CStore Scan': {
    #     'exec': ['l_input_rows', 'actual_rows', 'width', 'predicate_cost'],
    #     'mem': ['l_input_rows', 'actual_rows', 'width']
    # },
    # 'Vector Aggregate': {
    #     'exec': ['l_input_rows', 'actual_rows', 'width', 'agg_width'],
    #     'mem': ['l_input_rows', 'actual_rows', 'width', 'agg_width']
    # },
    # 'Vector Sort': {
    #     'exec': ['l_input_rows', 'actual_rows', 'width'],
    #     'mem': ['l_input_rows', 'actual_rows', 'width']
    # },
    # 'Vector Materialize': {
    #     'exec': ['l_input_rows', 'actual_rows', 'width'],
    #     'mem': ['l_input_rows', 'actual_rows', 'width']
    # },
    # 'Vector Hash Aggregate': {
    #     'exec': ['l_input_rows', 'width', 'agg_col', 'agg_width', 'disk_ratio'],
    #     'mem': ['actual_rows', 'width', 'agg_col', 'agg_width', 'hash_table_size', 'disk_ratio']
    # },
    # # 'Vector Hash Aggregate': {
    # #     'exec': ['l_input_rows', 'width', 'agg_col', 'agg_width', 'disk_ratio'],
    # #     'mem': ['actual_rows', 'width', 'agg_col', 'agg_width', 'disk_ratio'] + (['hash_table_size'] if USE_HASH_TABLE_SIZE_FEATURE else [])
    # # },
    # 'Vector Sonic Hash Aggregate': {
    #     'exec': ['l_input_rows', 'width', 'agg_col', 'agg_width', 'disk_ratio'],
    #     'mem': ['actual_rows', 'width', 'agg_col', 'agg_width', 'hash_table_size', 'disk_ratio']
    # },
    # # 'Vector Sonic Hash Aggregate': {
    # #     'exec': ['l_input_rows', 'width', 'agg_col', 'agg_width', 'disk_ratio'],
    # #     'mem': ['actual_rows', 'width', 'agg_col', 'agg_width',  'disk_ratio'] + (['hash_table_size'] if USE_HASH_TABLE_SIZE_FEATURE else [])
    # # },
    # 'Vector Hash Join': {
    #     'exec': ['l_input_rows', 'r_input_rows', 'actual_rows', 'width', 'jointype', 'predicate_cost', 'hash_table_size'],
    #     'mem': ['r_input_rows', 'width', 'hash_table_size']
    # },
    # # 'Vector Hash Join': {
    # #     'exec': ['l_input_rows', 'r_input_rows', 'actual_rows', 'width', 'jointype', 'predicate_cost'] + (['hash_table_size'] if USE_HASH_TABLE_SIZE_FEATURE else []),
    # #     'mem': ['r_input_rows', 'width'] + (['hash_table_size'] if USE_HASH_TABLE_SIZE_FEATURE else [])
    # # },
    # 'Vector Sonic Hash Join': {
    #     'exec': ['l_input_rows', 'r_input_rows', 'actual_rows', 'width', 'jointype', 'predicate_cost','hash_table_size'],
    #     'mem': ['r_input_rows', 'width', 'hash_table_size']
    # },
    # # 'Vector Sonic Hash Join': {
    # #     'exec': ['l_input_rows', 'r_input_rows', 'actual_rows', 'width', 'jointype', 'predicate_cost'] + (['hash_table_size'] if USE_HASH_TABLE_SIZE_FEATURE else []),
    # #     'mem': ['r_input_rows', 'width'] + (['hash_table_size'] if USE_HASH_TABLE_SIZE_FEATURE else [])
    # # },
    # 'Vector Streaming LOCAL GATHER': {
    #     'exec': ['l_input_rows',  'actual_rows', 'width'],
    #     'mem': ['l_input_rows', 'actual_rows', 'width']
    # },
    # 'Vector Streaming LOCAL REDISTRIBUTE': {
    #     'exec': ['l_input_rows',  'actual_rows', 'width'],
    #     'mem': ['l_input_rows', 'actual_rows', 'width']
    # },
    # 'Vector Streaming BROADCAST': {
    #     'exec': ['l_input_rows',  'actual_rows', 'width'],
    #     'mem': ['l_input_rows', 'actual_rows', 'width']
    # },
    # 'Vector SetOp': {
    #     'exec': ['l_input_rows',  'actual_rows', 'width'],
    #     'mem': ['l_input_rows', 'actual_rows', 'width']
    # },
    # 'Vector Append': {
    #     'exec': ['l_input_rows',  'actual_rows', 'width'],
    #     'mem': ['l_input_rows', 'actual_rows', 'width']
    # },
    # 'Aggregate': {
    #     'exec': ['l_input_rows', 'width', 'agg_col', 'agg_width'],
    #     'mem': ['l_input_rows', 'width', 'agg_col', 'agg_width']
    # },
    # 'Vector Sort Aggregate': {
    #     'exec': ['l_input_rows', 'width', 'agg_col', 'agg_width'],
    #     'mem': ['l_input_rows', 'width', 'agg_col', 'agg_width']
    # },
    # 'Hash Join': {
    #     'exec': ['l_input_rows', 'r_input_rows', 'actual_rows', 'width', 'jointype', 'predicate_cost', 'hash_table_size'],
    #     'mem': ['r_input_rows', 'width', 'jointype', 'hash_table_size']
    # },
    # # 'Hash Join': {
    # #     'exec': ['l_input_rows', 'r_input_rows', 'actual_rows', 'width', 'jointype', 'predicate_cost'] + (['hash_table_size'] if USE_HASH_TABLE_SIZE_FEATURE else []),
    # #     'mem': ['r_input_rows', 'jointype', 'width'] + (['hash_table_size'] if USE_HASH_TABLE_SIZE_FEATURE else [])
    # # },
    # 'Hash': {
    #     'exec': ['l_input_rows', 'actual_rows', 'width'],
    #     'mem': ['l_input_rows', 'actual_rows', 'width']
    # },
    # 'Append': {
    #     'exec': ['l_input_rows', 'actual_rows', 'width'],
    #     'mem': ['l_input_rows', 'actual_rows', 'width']
    # },

    # Add more operators and their corresponding feature sets here as needed
    # Notes:
    # - execution-time model keeps more runtime/throughput signals
    # - memory model focuses on row/byte volume + spill/driver pressure
    # - all features are taken from output.csv columns to avoid train/infer skew
    'ScanFilterProject': {
        'exec': ['l_input_rows', 'input_rows', 'output_rows', 'input_bytes', 'output_bytes',
                 'bytes_per_input_row', 'bytes_per_output_row', 'output_per_input_rows',
                 'add_input_calls', 'get_output_calls', 'blocked_ratio', 'dop', 'query_dop'],
        'mem':  ['l_input_rows', 'input_rows', 'output_rows', 'input_bytes', 'output_bytes',
                 'bytes_per_input_row', 'bytes_per_output_row', 'total_drivers',
                 'spilled_bytes', 'physical_written_bytes', 'dop', 'query_dop']
    },
    'Aggregate': {
        'exec': ['l_input_rows', 'input_rows', 'output_rows', 'input_bytes', 'output_bytes',
                 'output_per_input_rows', 'output_per_input_bytes', 'input_avg_rows_per_call',
                 'input_var_proxy', 'blocked_ratio', 'finish_calls', 'dop', 'query_dop'],
        'mem':  ['l_input_rows', 'input_rows', 'output_rows', 'input_bytes', 'output_bytes',
                 'total_drivers', 'spilled_bytes', 'physical_written_bytes',
                 'blocked_ratio', 'dop', 'query_dop']
    },
    'AssignUniqueId': {
        'exec': ['l_input_rows', 'input_rows', 'output_rows', 'input_bytes', 'output_bytes',
                 'add_input_calls', 'get_output_calls', 'blocked_ratio', 'dop', 'query_dop'],
        'mem':  ['l_input_rows', 'input_rows', 'output_rows', 'input_bytes', 'output_bytes',
                 'total_drivers', 'dop', 'query_dop']
    },
    'CrossJoin': {
        'exec': ['l_input_rows', 'r_input_rows', 'input_rows', 'output_rows', 'input_bytes',
                 'output_bytes', 'bytes_per_input_row', 'bytes_per_output_row',
                 'blocked_ratio', 'is_join', 'dop', 'query_dop'],
        'mem':  ['l_input_rows', 'r_input_rows', 'input_rows', 'output_rows', 'input_bytes',
                 'output_bytes', 'spilled_bytes', 'physical_written_bytes',
                 'total_drivers', 'dop', 'query_dop']
    },
    'EnforceSingleRow': {
        'exec': ['l_input_rows', 'input_rows', 'output_rows', 'input_bytes', 'output_bytes',
                 'get_output_calls', 'finish_calls', 'blocked_ratio', 'dop', 'query_dop'],
        'mem':  ['l_input_rows', 'input_rows', 'output_rows', 'input_bytes', 'output_bytes',
                 'total_drivers', 'dop', 'query_dop']
    },
    'FilterProject': {
        'exec': ['l_input_rows', 'input_rows', 'output_rows', 'input_bytes', 'output_bytes',
                 'output_per_input_rows', 'output_per_input_bytes', 'add_input_calls',
                 'get_output_calls', 'input_avg_rows_per_call', 'blocked_ratio', 'dop', 'query_dop'],
        'mem':  ['l_input_rows', 'input_rows', 'output_rows', 'input_bytes', 'output_bytes',
                 'bytes_per_input_row', 'bytes_per_output_row', 'total_drivers',
                 'spilled_bytes', 'physical_written_bytes', 'dop', 'query_dop']
    },
    'InnerJoin': {
        'exec': ['l_input_rows', 'r_input_rows', 'input_rows', 'output_rows', 'input_bytes',
                 'output_bytes', 'probe_keys', 'null_probe_keys', 'build_keys', 'null_build_keys',
                 'blocked_ratio', 'is_join', 'dop', 'query_dop'],
        'mem':  ['l_input_rows', 'r_input_rows', 'input_rows', 'output_rows', 'input_bytes',
                 'output_bytes', 'build_keys', 'probe_keys', 'spilled_bytes',
                 'physical_written_bytes', 'total_drivers', 'dop', 'query_dop']
    },
    'LeftJoin': {
        'exec': ['l_input_rows', 'r_input_rows', 'input_rows', 'output_rows', 'input_bytes',
                 'output_bytes', 'probe_keys', 'build_keys', 'blocked_ratio',
                 'is_join', 'dop', 'query_dop'],
        'mem':  ['l_input_rows', 'r_input_rows', 'input_rows', 'output_rows', 'input_bytes',
                 'output_bytes', 'build_keys', 'probe_keys', 'spilled_bytes',
                 'physical_written_bytes', 'total_drivers', 'dop', 'query_dop']
    },
    'LocalExchange': {
        'exec': ['l_input_rows', 'input_rows', 'output_rows', 'input_bytes', 'output_bytes',
                 'get_output_calls', 'blocked_ratio', 'is_exchange_like', 'dop', 'query_dop'],
        'mem':  ['l_input_rows', 'input_rows', 'output_rows', 'input_bytes', 'output_bytes',
                 'total_drivers', 'is_exchange_like', 'dop', 'query_dop']
    },
    'LocalMerge': {
        'exec': ['l_input_rows', 'input_rows', 'output_rows', 'input_bytes', 'output_bytes',
                 'get_output_calls', 'finish_calls', 'blocked_ratio', 'is_exchange_like', 'dop', 'query_dop'],
        'mem':  ['l_input_rows', 'input_rows', 'output_rows', 'input_bytes', 'output_bytes',
                 'total_drivers', 'spilled_bytes', 'physical_written_bytes', 'dop', 'query_dop']
    },
    'PartialSort': {
        'exec': ['l_input_rows', 'input_rows', 'output_rows', 'input_bytes', 'output_bytes',
                 'bytes_per_input_row', 'bytes_per_output_row', 'blocked_ratio',
                 'finish_calls', 'dop', 'query_dop'],
        'mem':  ['l_input_rows', 'input_rows', 'output_rows', 'input_bytes', 'output_bytes',
                 'spilled_bytes', 'physical_written_bytes', 'total_drivers', 'dop', 'query_dop']
    },
    'Project': {
        'exec': ['l_input_rows', 'input_rows', 'output_rows', 'input_bytes', 'output_bytes',
                 'add_input_calls', 'get_output_calls', 'blocked_ratio', 'dop', 'query_dop'],
        'mem':  ['l_input_rows', 'input_rows', 'output_rows', 'input_bytes', 'output_bytes',
                 'bytes_per_input_row', 'bytes_per_output_row', 'total_drivers', 'dop', 'query_dop']
    },
    'RemoteSource': {
        'exec': ['l_input_rows', 'input_rows', 'output_rows', 'input_bytes', 'output_bytes',
                 'raw_input_rows', 'raw_input_bytes', 'blocked_ratio', 'is_exchange_like', 'dop', 'query_dop'],
        'mem':  ['l_input_rows', 'input_rows', 'output_rows', 'input_bytes', 'output_bytes',
                 'raw_input_rows', 'raw_input_bytes', 'total_drivers', 'dop', 'query_dop']
    },
    'ScanFilter': {
        'exec': ['l_input_rows', 'input_rows', 'output_rows', 'raw_input_rows', 'input_bytes',
                 'raw_input_bytes', 'output_bytes', 'output_per_input_rows',
                 'add_input_calls', 'get_output_calls', 'blocked_ratio', 'dop', 'query_dop'],
        'mem':  ['l_input_rows', 'input_rows', 'output_rows', 'raw_input_rows', 'input_bytes',
                 'raw_input_bytes', 'output_bytes', 'bytes_per_input_row',
                 'bytes_per_output_row', 'total_drivers', 'dop', 'query_dop']
    },
    'ScanProject': {
        'exec': ['l_input_rows', 'input_rows', 'output_rows', 'raw_input_rows', 'input_bytes',
                 'raw_input_bytes', 'output_bytes', 'add_input_calls',
                 'get_output_calls', 'blocked_ratio', 'dop', 'query_dop'],
        'mem':  ['l_input_rows', 'input_rows', 'output_rows', 'raw_input_rows', 'input_bytes',
                 'raw_input_bytes', 'output_bytes', 'total_drivers', 'dop', 'query_dop']
    },
    'SemiJoin': {
        'exec': ['l_input_rows', 'r_input_rows', 'input_rows', 'output_rows', 'input_bytes',
                 'output_bytes', 'probe_keys', 'build_keys', 'blocked_ratio',
                 'is_join', 'dop', 'query_dop'],
        'mem':  ['l_input_rows', 'r_input_rows', 'input_rows', 'output_rows', 'input_bytes',
                 'output_bytes', 'build_keys', 'probe_keys', 'spilled_bytes',
                 'physical_written_bytes', 'total_drivers', 'dop', 'query_dop']
    },
    'TableScan': {
        'exec': ['l_input_rows', 'input_rows', 'output_rows', 'raw_input_rows', 'input_bytes',
                 'raw_input_bytes', 'output_bytes', 'bytes_per_input_row',
                 'add_input_calls', 'get_output_calls', 'blocked_ratio', 'is_leaf', 'dop', 'query_dop'],
        'mem':  ['l_input_rows', 'input_rows', 'output_rows', 'raw_input_rows', 'input_bytes',
                 'raw_input_bytes', 'output_bytes', 'bytes_per_input_row',
                 'total_drivers', 'is_leaf', 'dop', 'query_dop']
    },

}

# Presto native operators that may not exist in openGauss datasets.
# Keep them as independent operators instead of forcing semantic remapping.
PRESTO_NATIVE_OPERATORS = [
    'MergeOperator',
    'ExplainAnalyzeOperator',
    'TaskOutputOperator',
    'ExchangeOperator',
    'OrderBy',
    'LocalMerge',
    'CallbackSink',
    'PartitionedOutput',
    'LocalExchangeSourceOperator',
    'HashBuilderOperator',
    'LookupJoinOperator',
    'LocalExchangeSinkOperator',
    'Aggregation',
    'PartialAggregation',
    'NestedLoopJoinBuild',
    'NestedLoopJoinProbe',
]

def _extend_unique(target_list, values):
    for value in values:
        if value not in target_list:
            target_list.append(value)

# Ensure these operators can enter train/infer loops.
_extend_unique(operator_lists, PRESTO_NATIVE_OPERATORS)
_extend_unique(operator_type, PRESTO_NATIVE_OPERATORS)
_extend_unique(parallel_op, PRESTO_NATIVE_OPERATORS)
_extend_unique(dop_operators_exec, PRESTO_NATIVE_OPERATORS)
_extend_unique(dop_operators_mem, PRESTO_NATIVE_OPERATORS)
operator_encoding = {op_name: idx for idx, op_name in enumerate(operator_type)}

# Conservative materialization tags for common pipeline breakers.
# for _op in [
#     'ExchangeOperator',
#     'LocalExchangeSourceOperator',
#     'LocalExchangeSinkOperator',
#     'PartitionedOutput',
#     'OrderBy',
#     'Aggregation',
#     'PartialAggregation',
#     'HashBuilderOperator',
#     'LocalMerge',
# ]:
#     materialized_operator_types.add(_op)

# Shared enriched feature set for Presto-native operators.
# Prefer columns already present in plan_info.csv to maximize model signal.
PRESTO_COMMON_EXEC_FEATURES = [
    'l_input_rows', 'r_input_rows', 'input_rows', 'raw_input_rows', 'output_rows',
    'input_bytes', 'raw_input_bytes', 'output_bytes',
    'output_per_input_rows', 'output_per_input_bytes',
    'bytes_per_input_row', 'bytes_per_output_row',
    'blocked_ratio', 'add_input_calls', 'get_output_calls', 'finish_calls',
    'total_drivers', 'spilled_bytes', 'physical_written_bytes',
    'build_keys', 'null_build_keys', 'probe_keys', 'null_probe_keys',
    'input_avg_rows_per_call', 'input_var_proxy',
    'child_count', 'is_leaf', 'is_exchange_like', 'is_join',
    'dop', 'query_dop'
]

PRESTO_COMMON_MEM_FEATURES = [
    'l_input_rows', 'r_input_rows', 'input_rows', 'raw_input_rows', 'output_rows',
    'input_bytes', 'raw_input_bytes', 'output_bytes',
    'bytes_per_input_row', 'bytes_per_output_row',
    'blocked_ratio', 'total_drivers',
    'spilled_bytes', 'physical_written_bytes',
    'build_keys', 'null_build_keys', 'probe_keys', 'null_probe_keys',
    'input_avg_rows_per_call', 'input_var_proxy',
    'child_count', 'is_leaf', 'is_exchange_like', 'is_join',
    'dop', 'query_dop'
]

# Upgrade existing Presto-native operator features to enriched feature set.
for _op in PRESTO_NATIVE_OPERATORS:
    dop_operator_features[_op] = {
        'exec': PRESTO_COMMON_EXEC_FEATURES,
        'mem': PRESTO_COMMON_MEM_FEATURES,
    }

# 全局特征列表 - 分别收集exec和mem特征
all_exec_features = set()
all_mem_features = set()

# 收集所有dop_operator_features中的特征
for op_type, features in dop_operator_features.items():
    all_exec_features.update(features.get('exec', []))
    all_mem_features.update(features.get('mem', []))

# 收集所有no_dop_operator_features中的特征
for op_type, features in no_dop_operator_features.items():
    all_exec_features.update(features.get('exec', []))
    all_mem_features.update(features.get('mem', []))

# 创建全局特征列表（分别用于exec和mem模型）
global_exec_feature_list = sorted(list(all_exec_features))
global_mem_feature_list = sorted(list(all_mem_features))

# 这里定义每个算子训练是的轮数。
dop_train_epochs = {
    'CStore Scan': {
        'exec': 150,
        'mem': 20
    },
    'Vector Aggregate': {
        'exec': 100,
        'mem': 100
    },
    'Vector Sort': {
        'exec': 100,
        'mem': 100
    },
    'Vector Materialize': {
        'exec': 100,
        'mem': 100
    },
    'Vector Hash Aggregate': {
        'exec': 100,
        'mem': 100
    },
    'Vector Sonic Hash Aggregate': {
        'exec': 200,
        'mem': 100
    },
    'Vector Hash Join': {
        'exec': 200,
        'mem': 100
    },
    'Vector Sonic Hash Join': {
        'exec': 100,
        'mem': 100
    },
    'Vector Streaming LOCAL GATHER': {
        'exec': 100,
        'mem': 100
    },
    'Vector Streaming LOCAL REDISTRIBUTE': {
        'exec': 120,
        'mem': 100
    },
    'Vector Streaming BROADCAST': {
        'exec': 100,
        'mem': 100
    },
    'Vector SetOp': {
        'exec': 100,
        'mem': 100
    },
    'Vector Append': {
        'exec': 100,
        'mem': 100
    },
    'Aggregate': {
        'exec': 100,
        'mem': 50
    },
    'Append': {
        'exec': 100,
        'mem': 50
    },
    'Hash Join': {
        'exec': 100,
        'mem': 50
    },
    'Hash': {
        'exec': 100,
        'mem': 50
    },
    'Vector Append': {
        'exec': 100,
        'mem': 50
    },
    'Vector Sort Aggregate': {
        'exec': 100,
        'mem': 50
    },

    # Add more operators and their corresponding feature sets here as needed
    'ScanFilterProject': {
        'exec': 100,
        'mem': 50
     },
    'Aggregate': {
        'exec': 100,
        'mem': 50
     },
    'AssignUniqueId': {
        'exec': 400,
        'mem': 50
    },
    'CrossJoin': {
        'exec': 100,
        'mem': 50
    },
    'EnforceSingleRow': {
        'exec': 300,
        'mem': 50
    },
    'FilterProject': {
        'exec': 220,
        'mem': 50
    },
    'InnerJoin': {
        'exec': 100,
        'mem': 50
    },
    'LeftJoin': {
        'exec': 100,
        'mem': 50
    },
    'LocalExchange': {
        'exec': 100,
        'mem': 50
    },
    'LocalMerge': {
        'exec': 100,
        'mem': 50
    },
    'PartialSort': {
        'exec': 100,
        'mem': 50
    },
    'Project': {
        'exec': 100,
        'mem': 50
    },
    'RemoteSource': {
        'exec': 100,
        'mem': 50
    },
    'ScanFilter': {
        'exec': 100,
        'mem': 50
    },
    'ScanProject': {
        'exec': 100,
        'mem': 50
    },
    'SemiJoin': {
        'exec': 100,
        'mem': 50
    },
    'TableScan': {
        'exec': 400,
        'mem': 50
    },
    'MergeOperator': {
        'exec': 200,
        'mem': 50
    },
    'ExplainAnalyzeOperator': {
        'exec': 200,
        'mem': 50
    },
    'TaskOutputOperator': {
        'exec': 200,
        'mem': 50
    },
    'ExchangeOperator': {
        'exec': 300,
        'mem': 50
    },
    'OrderBy': {
        'exec': 220,
        'mem': 50
    },
    'PartitionedOutput': {
        'exec': 260,
        'mem': 50
    },
    'HashBuilderOperator': {
        'exec': 320,
        'mem': 50
    },
    'LocalExchangeSinkOperator': {
        'exec': 200,
        'mem': 50
    },
    'NestedLoopJoinBuild': {
        'exec': 200,
        'mem': 50
    },
    'NestedLoopJoinProbe': {
        'exec': 200,
        'mem': 50
    }
}

# Ensure newly introduced operators always have training epoch config.
for _op in PRESTO_NATIVE_OPERATORS:
    if _op not in dop_train_epochs:
        dop_train_epochs[_op] = {
            'exec': 100,
            'mem': 50,
        }

# Override difficult exec operators with longer training budget.
_difficult_exec_epochs = {
    'OrderBy': 220,
    'PartitionedOutput': 260,
    'LocalExchangeSourceOperator': 300,
    'ExchangeOperator': 300,
    'Aggregation': 300,
    'PartialAggregation': 300,
    'HashBuilderOperator': 400,
    'LookupJoinOperator': 350,
}
for _op, _exec_epochs in _difficult_exec_epochs.items():
    if _op not in dop_train_epochs:
        dop_train_epochs[_op] = {'exec': _exec_epochs, 'mem': 50}
    else:
        dop_train_epochs[_op]['exec'] = _exec_epochs