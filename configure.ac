#
# Preamble
#

AC_INIT([allpro88-fx2-soft],[2.0.0],[kipp@g.ecc.u-tokyo.ac.jp],[allpro88])
AC_COPYRIGHT([Copyright (C) The authors (see source code for details)])
# a file whose existance can be used to use to check that we are in the
# top-level directory of the source tree
AC_CONFIG_SRCDIR([gnuscripts/ltmain.sh])
AC_CONFIG_AUX_DIR([gnuscripts])
AC_CONFIG_MACRO_DIR([gnuscripts])
AM_INIT_AUTOMAKE([1.9 tar-ustar foreign])
AUTOMAKE_OPTIONS="${AUTOMAKE_OPTIONS} --add-missing --copy"

AC_CONFIG_FILES([\
	Makefile \
	udev/Makefile \
	utils/Makefile \
	utils/bin/Makefile \
	utils/python/Makefile \
	utils/python/allpro88/Makefile \
	utils/python/allpro88/paths.py \
])


AC_PROG_INSTALL


#
# Extra directories
#


AC_SUBST([pkglocalstatedir],["\${localstatedir}/${PACKAGE}"])


#
# Check for Python
#


AC_SUBST([MIN_PYTHON_VERSION], ["3.6"])
AM_PATH_PYTHON(["$MIN_PYTHON_VERSION"],,)
AX_PYTHON_DEVEL()
# hack to remove default lib dirs from PYTHON_LIBS.  only tested on Debian
# and SL6.  FIXME:  find a way to do this properly
PYTHON_LIBS=[`echo "$PYTHON_LIBS" | sed -e "s?-L/usr/lib[^[:space:]]*??g"`]


#
# Output configure information
#


AC_PROG_MAKE_SET
AC_OUTPUT

