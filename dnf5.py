import sys
import libdnf5

# TODO DNF5 not-implemented features:
# - some ensure modifiers
#   - allow_downgrade
# - autoremove
#   - listing unneeded pkgs not implemented yet
# - cache update
#   - automatic in DNF5
#   - any modification needed for the Ansible purposes?

# TODO examples:
# - configuration options like enable-repo
# - limit upgrade packages only to bugfix / security ones
# - update_only

# DNF5 example usecases for the Ansible module
#
# Usecase: list all packages installed on the system
# python3 dnf5.py list installed
#
# Usecase: list all packages matching the given specs
# python3 dnf5.py list rpm zlib*
#
# Usecase: install the 'gdk-pixbuf2-devel' package
# python3 dnf5.py ensure present gdk-pixbuf2-devel
#
# Usecase: update the 'zlib' package
# python3 dnf5.py ensure latest zlib

class Dnf5AnsibleUsecases:
    def __init__(self):
        self.base = self._prepare_base()
        self._prepare_repos()
    
    def _is_spec_installed(self, spec):
        settings = libdnf5.base.ResolveSpecSettings()
        query = libdnf5.rpm.PackageQuery(self.base)
        query.filter_installed()
        match, nevra = query.resolve_pkg_spec(spec, settings, True)
        return match
    
    # Note: Downloading part to be simplified
    # See https://github.com/rpm-software-management/dnf5/issues/277
    def _download_missing_packages(self, transaction):
        downloader = libdnf5.repo.PackageDownloader()

        for pkg in transaction.get_transaction_packages():
            if libdnf5.base.transaction.transaction_item_action_is_inbound(pkg.get_action()) and \
               pkg.get_package().get_repo().get_type() != libdnf5.repo.Repo.Type_COMMANDLINE:
                downloader.add(pkg.get_package())

        downloader.download(True, True)
    
    def _do_transaction(self, transaction):
        # Add download / transaction callbacks, triggers
        # See 'dnf5/test/python3/libdnf5/tutorial/transaction/transaction.py'
        
        self._download_missing_packages(transaction)
        
        # Add other transaction metadata to be stored in the history DB
        # transaction.set_comment("Some comment")
        # transaction.set_user_id(12345)
        
        transaction.set_description("Ansible")
        transaction.run()

    def _package_dict(self, package):
        result = {
            'name': package.get_name(),
            'arch': package.get_arch(),
            'epoch': str(package.get_epoch()),
            'release': package.get_release(),
            'version': package.get_version(),
            'repo': package.get_repo_id()}

        return result

    def _prepare_base(self):
        base = libdnf5.base.Base()
        base.load_config_from_file()
        
        # Override any configuration options like this:
        # conf = base.get_config()
        # conf.installroot().set('/path/to/installroot')
        # conf.skip_broken().set(True)
        #
        # Note: This is a subject of potential rewrite
        # See https://github.com/rpm-software-management/dnf5/issues/236

        base.setup()

        return base

    def _prepare_repos(self):
        sack = self.base.get_repo_sack()
        sack.create_repos_from_system_configuration()
        sack.update_and_load_enabled_repos(True)

    def list(self, args):
        """Package listings usecase

        Args:
            args(list[str]): Arguments in one of the following forms:
            - a single argument meaning the type of the listing from ['installed', 'upgrades', 'available', 'repos', 'repositories']
            - list of specs to query any matching packages
            
        Returns:
            list[dict[str, str]]: List of matching packages in a dict form
        """
        cmd = args[0]
        if cmd in ['installed', 'upgrades', 'available']:
            query = libdnf5.rpm.PackageQuery(self.base)
            getattr(query, 'filter_' + cmd)()
            results = [self._package_dict(package) for package in query]
            return results
        elif cmd in ['repos', 'repositories']:
            query = libdnf5.repo.RepoQuery(self.base)
            query.filter_enabled(True)
            results = [{'repoid': repo.get_id(), 'state': 'enabled'} for repo in query]
            return results
        else:
            resolve_spec_settings = libdnf5.base.ResolveSpecSettings()
            results = []
            for spec in args:
                query = libdnf5.rpm.PackageQuery(self.base)
                query.resolve_pkg_spec(spec, resolve_spec_settings, True)
                results += [self._package_dict(package) for package in query]
            return results
    
    def ensure(self, cmd, specs):
        """Install, update, remove usecase

        Args:
            cmd (str): Action command to be executed from ['installed', 'present', 'latest', 'absent']
            specs (list[str]): Specs to be processed within the action
        """
        goal = libdnf5.base.Goal(self.base)
        if cmd == 'latest' and specs[0] == '*':
            goal.add_rpm_upgrade()
        elif cmd in ['installed', 'present']:
            for spec in specs:
                goal.add_install(spec)
        elif cmd == 'latest':
            for spec in specs:
                goal.add_upgrade(spec)
        elif cmd == 'absent':
            for spec in specs:
                goal.add_remove(spec)

        # Apply behavior modifiers like this:
        # goal.set_allow_erasing(True)

        transaction = goal.resolve()
        self._do_transaction(transaction)


def main():
    if len(sys.argv) < 3:
        print('Invalid args')
        sys.exit(1)

    command = sys.argv[1]
    args = sys.argv[2:]

    ansible = Dnf5AnsibleUsecases()

    if command == 'list':
        items = ansible.list(args)
        print(items)
    elif command == 'ensure':
        ansible.ensure(args[0], args[1:])


if __name__ == '__main__':
    main()
