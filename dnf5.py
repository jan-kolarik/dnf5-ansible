import sys
import libdnf5

# TODO DNF5 not-implemented features:
# - some ensure modifiers
#   - allow_downgrade - now it is always True
# - autoremove
#   - listing unneeded pkgs not implemented yet
#   - https://github.com/rpm-software-management/dnf5/issues/132
# - cache update
#   - automatic in DNF5
#   - any modification needed for the Ansible purposes?
# - cacheonly
#   - https://github.com/rpm-software-management/dnf5/issues/191
# - disable_plugin, enable_plugin

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

    def _do_transaction(self, transaction):
        # Add download / transaction callbacks, triggers
        # See 'dnf5/test/python3/libdnf5/tutorial/transaction/transaction.py'

        # Download all needed packages
        # Optionally specify the 'download_dir' parameter
        transaction.download()

        # Add other transaction metadata to be stored in the history DB
        # transaction.set_comment("Some comment")
        # transaction.set_user_id(12345)
        transaction.set_description("Ansible")

        # Execute the actual transaction
        result = transaction.run()

        # Print any problems during transaction execution
        if result == libdnf5.base.Transaction.TransactionRunResult_SUCCESS:
            print('Transaction completed successfully.')
        else:
            print(f'Transaction was not successful: {transaction.transaction_result_to_string(result)}')
            if transaction.get_transaction_problems():
                print('Following issues happened when executing the transaction:')
                for log in transaction.get_transaction_problems():
                    print(log)

    def _package_dict(self, package):
        result = {
            'name': package.get_name(),
            'arch': package.get_arch(),
            'epoch': str(package.get_epoch()),
            'release': package.get_release(),
            'version': package.get_version(),
            'repo': package.get_repo_id()}

        return result

    def _override_base_conf(self, base):
        # Note: This is a subject of potential rewrite
        # See https://github.com/rpm-software-management/dnf5/issues/236

        conf = base.get_config()
        conf.best().set(True)
        conf.disable_excludes().set([])
        conf.excludepkgs().set([])
        conf.gpgcheck().set(False)
        conf.install_weak_deps().set(True)
        conf.installroot().set('/root/dir/')
        conf.repo_gpgcheck().set(False)
        conf.skip_broken().set(True)
        conf.sslverify().set(True)

        vars = base.get_vars()
        vars.set('releasever', '38')

    def _prepare_base(self):
        base = libdnf5.base.Base()

        # Change config file path like this:
        # base.get_config().config_file_path().set('path')

        base.load_config_from_file()

        # Override any configuration options here like this:
        # self._override_base_conf(base)

        base.setup()

        return base

    def _enable_repos(self, repos):
        repo_query = libdnf5.repo.RepoQuery(self.base)
        repo_query.filter_id(repos)
        for repo in repo_query:
            repo.enable()

    def _disable_repos(self, repos):
        repo_query = libdnf5.repo.RepoQuery(self.base)
        repo_query.filter_id(repos)
        for repo in repo_query:
            repo.disable()

    def _create_goal_job_settings(self):
        settings = libdnf5.base.GoalJobSettings()

        # Apply security options like this:
        # advisory_query = libdnf5.advisory.AdvisoryQuery(self.base)
        # advisory_query.filter_type('bugfix')
        # settings.set_advisory_filter(advisory_query)

        return settings

    def _prepare_repos(self):
        sack = self.base.get_repo_sack()
        sack.create_repos_from_system_configuration()

        # Enable/disable repos here like this:
        # self._disable_repos(['updates'])
        # self._enable_repos(list)

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
        settings = self._create_goal_job_settings()

        if cmd == 'latest' and specs[0] == '*':
            goal.add_rpm_upgrade(settings)
        elif cmd in ['installed', 'present']:
            for spec in specs:
                goal.add_install(spec, settings)
        elif cmd == 'latest':
            for spec in specs:
                # Filter only installed packages on update_only like this:
                # if update_only and self._is_spec_installed(spec):
                goal.add_upgrade(spec, settings)
        elif cmd == 'absent':
            for spec in specs:
                goal.add_remove(spec, settings)

        # Apply behavior modifiers like this:
        # goal.set_allow_erasing(True)

        # Resolve the transaction goal
        transaction = goal.resolve()

        # Print any problems during transaction resolving
        if transaction.get_problems():
            print('Following issues happened when resolving the transaction:')
            for log in transaction.get_resolve_logs_as_strings():
                print(log)
        else:
            print('Transaction resolved correctly.')

        # Print transaction summary
        ts_pkgs = transaction.get_transaction_packages()
        if ts_pkgs:
            print('Transaction summary:')
            for pkg in ts_pkgs:
                print(f'Package "{pkg.get_package().get_nevra()}". '
                      f'Action "{libdnf5.base.transaction.transaction_item_action_to_string(pkg.get_action())}".')
        else:
            print('Transaction is empty.')

        # Execute the transaction
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
