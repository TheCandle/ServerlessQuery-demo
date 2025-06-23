%type <list> tsql_stmtmulti

%type <list> identity_seed_increment
%type <node> DBCCCheckIdentStmt DBCCStmt tsql_stmt tsql_CreateProcedureStmt tsql_IndexStmt tsql_TransactionStmt

%token <keyword> CHECKIDENT DBCC NO_INFOMSGS NORESEED RESEED SAVE TRAN TSQL_CLUSTERED TSQL_NONCLUSTERED TSQL_COLUMNSTORE
%type <keyword>  tsql_opt_clustered tsql_opt_columnstore tsql_unique_clustered tsql_primary_key_clustered
%token <str>	TSQL_ATAT_IDENT
%type <boolean> opt_with_no_infomsgs tsql_opt_unique_clustered
%type <node> TSQL_AnonyBlockStmt TSQL_CreateFunctionStmt TSQL_DoStmt
%type <str> tsql_opt_transaction_name
%type <keyword> tsql_transaction_keywords
%token TSQL_UNIQUE_CLUSTERED TSQL_UNIQUE_NONCLUSTERED TSQL_PRIMAY_KEY_NONCLUSTERED TSQL_PRIMAY_KEY_CLUSTERED