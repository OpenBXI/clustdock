###############################################################################
# $Revision: 1.86 $
# $Date: 2011/07/06 16:54:26 $
###############################################################################

#TODO: define your package name
%define name clustdock

# Bull software starts with 1.1-Bull.1.0
# For versionning policy, please see wiki:
# http://intran0x.frec.bull.fr/projet/HPC/wiki_etudes/index.php/How_to_generate_RPM#Bull_rpm_NAMING_CONVENTION
%define version 1.2.0

# Using the .snapshot suffix helps the SVN tagging process.
# Please run <your_svn_checkout>/devtools/packaged/bin/auto_tag -m
# to get the auto_tag man file
# and to understand the SVN tagging process.
# If you don't care, then, just starts with Bull.1.0%{?dist}.%{?revision}snapshot
# and run 'make tag' when you want to tag.
%define release Bull.5.0%{?dist}.%{?revision}snapshot

# Warning: Bull's continuous compilation tools refuse the use of
# %release in the src_dir variable!
%define src_dir %{name}-%{version}
%define src_tarall %{src_dir}.tar.gz

Prefix: /etc
Prefix: /usr

# Other custom variables
%define src_conf_dir conf
%define src_bin_dir bin
%define src_lib_dir lib
%define src_doc_dir doc
%define target_systemd_dir %{?systemd_dir}%{!?systemd_dir:%(pkg-config systemd --variable=systemdsystemunitdir)}

%define target_conf_dir /etc
%define target_prefix  /usr/
%define target_bin_dir  %{target_prefix}bin
%define target_python_lib_dir %{python2_sitearch}
%define target_perllib_dir  %perl_vendorlib
%define target_man_dir  %{_mandir}
%define target_data_dir  %{target_prefix}/share/
%define target_doc_dir  %{target_data_dir}doc/%{name}
# @TODO : Support cases where BXI_BUILD_{SUB,}DIR variables are not defined
#         Attempt to get tagfiles from installed doc packages
%define src_tagfiles_prefix %{?tagfiles_prefix}%{?!tagfiles_prefix:%{bxi_build_dir}}
%define src_tagfiles_suffix %{?tagfiles_suffix}%{?!tagfiles_suffix:%{bxi_build_subdir}/packaged/doc/doxygen.tag}
%define target_htmldirs_prefix ../../
%define target_htmldirs_suffix /last/

# TODO: Give your summary
Summary:	Virtual Cluster provisioning tool
Name:		%{name}
Version:	%{version}
Release:	%{release}
Source:		%{src_tarall}
# Perform a 'cat /usr/share/doc/rpm-*/GROUPS' to get a list of available
# groups. Note that you should be in the corresponding PDP to get the
# most accurate information!
# TODO: Specify the category your software belongs to
Group:		Development/System
BuildRoot:	%{_tmppath}/%{name}-root
# Automatically filled in by PDP: it should not appear therefore!
#Packager:	Bull <help@bull.net>
Distribution:	Bull HPC

# Automatically filled in by PDP: it should not appear therefore!
#Vendor:         Bull
License:        'Bull S.A.S. proprietary : All rights reserved'
BuildArch:	x86_64
URL:            https://novahpc.frec.bull.fr

#TODO: What do you provide
Provides: %{name}
#Conflicts:
#TODO: What do you require
Requires: zeromq
Requires: python-msgpack >= 0.4.1

#Requires: bxibase >= 3.2.0
#BuildRequires: flex == 2.5.37

#TODO: Give a description (seen by rpm -qi) (No more than 80 characters)
%description
ClustDock unified solution to provision libvirt/docker clusters on the fly.

%package doc
Summary: ClustDock Documentation
#TODO: Give a description (seen by rpm -qi) (No more than 80 characters)
%description doc
ClustDock unified solution to provision libvirt/docker clusters on the fly.


%package server
Summary: ClustDock Server
#TODO: Give a description (seen by rpm -qi) (No more than 80 characters)

Requires: %{name} >= %{version}

Requires: python-signalfd
Requires: clustershell
Requires: libvirt-python
Requires: libguestfs-tools
Requires: python-ipaddr
Requires: python-lxml

%description server
ClustDock unified solution Server provisionning libvirt/docker clusters on the fly.


###############################################################################
# Prepare the files to be compiled
%prep
#%setup -q -n %{name}
test "x$RPM_BUILD_ROOT" != "x" && rm -rf $RPM_BUILD_ROOT
%setup

%configure --disable-debug --with-systemdsysdir=%{target_systemd_dir} --datadir=%{target_data_dir} %{?checkdoc} \
    --with-tagfiles-prefix=%{src_tagfiles_prefix} \
    --with-tagfiles-suffix=%{src_tagfiles_suffix} \
    --with-htmldirs-prefix=%{target_htmldirs_prefix} \
    --with-htmldirs-suffix=%{target_htmldirs_suffix}
###############################################################################
# The current directory is the one main directory of the tar
# Order of upgrade is:
#%pretrans new
#%pre new
#install new
#%post new
#%preun old
#delete old
#%postun old
#%posttrans new
%build
%{__make}

%install
%{__make} install DESTDIR=$RPM_BUILD_ROOT  %{?mflags_install}
mkdir -p $RPM_BUILD_ROOT/%{target_doc_dir}
cp ChangeLog $RPM_BUILD_ROOT/%{target_doc_dir}


%post

%post doc
rm -f %{target_doc_dir}/last
ls %{target_doc_dir} \
| grep -q '^[0-9]\+[0-9.]*[0-9]\+$' \
&& ln -s $( \
    ls %{target_doc_dir} | \
        grep '^[0-9]\+[0-9.]*[0-9]\+$' | \
        sort | tail -n1 \
) %{target_doc_dir}/last \
|| true

%postun

%postun doc
rm -f %{target_doc_dir}/last
ls %{target_doc_dir} \
| grep -q '^[0-9]\+[0-9.]*[0-9]\+$' \
&& ln -s $( \
    ls %{target_doc_dir} | \
        grep '^[0-9]\+[0-9.]*[0-9]\+$' | \
        sort | tail -n1 \
) %{target_doc_dir}/last \
|| true

%preun

%clean
cd /tmp
rm -rf $RPM_BUILD_ROOT/%{name}-%{version}
test "x$RPM_BUILD_ROOT" != "x" && rm -rf $RPM_BUILD_ROOT

###############################################################################
# Specify files to be placed into the package
%files
%defattr(-,root,root)
%{target_bin_dir}/clustdock
%{target_python_lib_dir}/%{name}/client*
%{target_python_lib_dir}/%{name}/__init__.*

%config(noreplace) %{target_conf_dir}/clustdock.conf

%doc
    %{target_doc_dir}/ChangeLog
    %{target_doc_dir}/conf/clustdock.conf

%files server
%{target_bin_dir}/clustdockd
%{target_systemd_dir}/clustdockd.service
%{target_python_lib_dir}/%{name}/[!c_]*

%config(noreplace) %{target_conf_dir}/clustdockd.conf

%doc
    %{target_doc_dir}/conf/clustdockd.conf
    %{target_doc_dir}/conf/clustdock-hook.example
# Changelog is automatically generated (see Makefile)
# The %doc macro already contain a default path (usually /usr/doc/)
# See:
# http://www.rpm.org/max-rpm/s1-rpm-inside-files-list-directives.html#S3-RPM-INSIDE-FLIST-DOC-DIRECTIVE for details
# %doc ChangeLog
# or using an explicit path:


#%{target_bin_dir}/bin1
#%{target_bin_dir}/prog2
#%{target_bin_dir}/exe3

%files doc
    %{target_doc_dir}/%{version}/

# %changelog is automatically generated by 'make log' (see the Makefile)
##################### WARNING ####################
## Do not add anything after the following line!
##################################################
%changelog
