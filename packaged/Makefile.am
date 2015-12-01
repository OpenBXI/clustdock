SUBDIRS=doc lib


sysconfigdir=$(sysconfdir)
dist_sysconfig_DATA=\
					conf/clustdock.conf

nobase_dist_doc_DATA=\
					 conf/clustdock.conf

dist_bin_SCRIPTS=\
				 bin/clustdock

if CD_SERVER 
if HAVE_SYSTEMD
dist_systemdsys_DATA=\
					 conf/clustdockd.service
endif

dist_sysconfig_DATA+=\
					conf/clustdockd.conf

nobase_dist_doc_DATA+=\
					 conf/clustdockd.conf\
					 conf/clustdock-hook.example

dist_bin_SCRIPTS+=\
				 bin/clustdockd
EXTRA_DIST=\
		   conf/clustdockd.service
endif
