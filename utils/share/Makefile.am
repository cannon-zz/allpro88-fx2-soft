pkgdata_DATA = \
	logic_tester_database.tar.gz

logic_tester_database.tar.gz : logic_tester_database/*
	@AMTAR@ -czf logic_tester_database.tar.gz logic_tester_database/

clean-local :
	rm -vf logic_tester_database.tar.gz
