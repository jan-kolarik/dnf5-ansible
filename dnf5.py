import sys
import libdnf5

# TODO DNF5 not-implemented features:
# - allow_downgrade - now it is always True
#   - https://github.com/rpm-software-management/dnf5/issues/388
# - cacheonly
#   - https://github.com/rpm-software-management/dnf5/issues/191
# - gpg signatures checking and recovery process
#   - https://github.com/rpm-software-management/dnf5/issues/386

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
        # TODO: To be improved?
        # If callbacks objects are defined inside the local functions,
        # they are garbage collected when going out of the scope.
        # Therefore using this helper container...
        self.callbacks = set()
        self.base = self._prepare_base()
        self._prepare_logging()
        self._prepare_repos()
        # Add download callbacks like this:
        # self._add_downloader_callbacks()

    def _is_spec_installed(self, spec):
        settings = libdnf5.base.ResolveSpecSettings()
        query = libdnf5.rpm.PackageQuery(self.base)
        query.filter_installed()
        match, nevra = query.resolve_pkg_spec(spec, settings, True)
        return match

    def _add_repos_callbacks(self):
        repo_query = libdnf5.repo.RepoQuery(self.base)
        repo_query.filter_enabled(True)
        for repo in repo_query:
            callbacks = RepoCallbacks(repo.get_id())
            self.callbacks.add(callbacks)
            repo.set_callbacks(libdnf5.repo.RepoCallbacksUniquePtr(callbacks))

    def _add_downloader_callbacks(self):
        downloader_callbacks = PackageDownloadCallbacks()
        self.callbacks.add(downloader_callbacks)
        self.base.set_download_callbacks(libdnf5.repo.DownloadCallbacksUniquePtr(downloader_callbacks))

    def _add_transaction_callbacks(self, transaction):
        transaction_callbacks = TransactionCallbacks()
        self.callbacks.add(transaction_callbacks)
        transaction_callbacks_ptr = libdnf5.rpm.TransactionCallbacksUniquePtr(transaction_callbacks)
        transaction.set_callbacks(transaction_callbacks_ptr)

    def _do_transaction(self, transaction):
        # Add transaction callbacks like this:
        # self._add_transaction_callbacks(transaction)

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
        conf = base.get_config()
        conf.best = True
        conf.clean_requirements_on_remove = True
        conf.disable_excludes = []
        conf.excludepkgs = []
        conf.gpgcheck = False
        conf.install_weak_deps = True
        conf.installroot = '/root/dir/'
        conf.repo_gpgcheck = False
        conf.skip_broken = True
        conf.sslverify = True

        vars = base.get_vars()
        vars.set('releasever', '38')

    def _prepare_base(self):
        base = libdnf5.base.Base()

        # Change config file path like this:
        # base.get_config().config_file_path = 'path'

        base.load_config_from_file()

        # Override any configuration options here like this:
        # self._override_base_conf(base)

        base.setup()

        return base

    def _enable_repos(self, repos):
        repo_query = libdnf5.repo.RepoQuery(self.base)
        repo_query.filter_id(repos, libdnf5.common.QueryCmp_IGLOB)
        for repo in repo_query:
            repo.enable()

    def _disable_repos(self, repos):
        repo_query = libdnf5.repo.RepoQuery(self.base)
        repo_query.filter_id(repos, libdnf5.common.QueryCmp_IGLOB)
        for repo in repo_query:
            repo.disable()

    def _create_goal_job_settings(self):
        settings = libdnf5.base.GoalJobSettings()

        # Apply security options like this:
        # advisory_query = libdnf5.advisory.AdvisoryQuery(self.base)
        # advisory_query.filter_type('bugfix')
        # settings.set_advisory_filter(advisory_query)

        # Apply additional resolve settings, like matching groups by their name:
        # settings.group_with_name = True

        return settings

    def _prepare_repos(self):
        sack = self.base.get_repo_sack()
        sack.create_repos_from_system_configuration()

        # Enable/disable repos here like this:
        # self._disable_repos('*')
        # self._disable_repos(['fedora', 'updates'])
        # self._enable_repos('fedora')

        # Add repository callbacks like this:
        # self._add_repos_callbacks()

        sack.update_and_load_enabled_repos(True)

    def _prepare_logging(self):
        # Enable logging into file defined in configuration
        # Add libraries logging with global logger
        log_router = self.base.get_logger()
        global_logger = libdnf5.logger.GlobalLogger()
        global_logger.set(log_router.get(), libdnf5.logger.Logger.Level_DEBUG)
        logger = libdnf5.logger.create_file_logger(self.base)
        log_router.add_logger(logger)

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
        elif cmd == 'autoremove':
            query = libdnf5.rpm.PackageQuery(self.base)
            query.filter_installed()
            query.filter_unneeded()
            for pkg in query:
                goal.add_rpm_remove(pkg, settings)

        # Apply behavior modifiers like this:
        # goal.set_allow_erasing(True)

        # Resolve the transaction goal
        transaction = goal.resolve()

        # Print any problems related to package signatures
        ts_pkgs = transaction.get_transaction_packages()
        if ts_pkgs:
            rpm_sign = libdnf5.rpm.RpmSignature(self.base)
            for ts_pkg in transaction.get_transaction_packages():
                pkg = ts_pkg.get_package()
                result = rpm_sign.check_package_signature(pkg)
                if result != libdnf5.rpm.RpmSignature.CheckResult_OK:
                    print(f'Failed to validate package signature for "{pkg.get_nevra()}" '
                          f'with error "{result}".')

        # Print any problems during transaction resolving
        if transaction.get_problems():
            print('Following issues happened when resolving the transaction:')
            for log in transaction.get_resolve_logs_as_strings():
                print(log)
        else:
            print('Transaction resolved correctly.')

        # Print transaction summary
        if ts_pkgs:
            print('Transaction summary:')
            for pkg in ts_pkgs:
                print(f'Package "{pkg.get_package().get_nevra()}". '
                      f'Action "{libdnf5.base.transaction.transaction_item_action_to_string(pkg.get_action())}".')
        else:
            print('Transaction is empty.')

        # Execute the transaction
        self._do_transaction(transaction)


# Example implementation of repository metadata callbacks
class RepoCallbacks(libdnf5.repo.RepoCallbacks):
    def __init__(self, repo_id):
        self.repo_id = repo_id
        super().__init__()
    def end(self, error):
        if error:
            print(f'Repo "{self.repo_id}" load error: {error}')


# Example implementation of download callbacks
class PackageDownloadCallbacks(libdnf5.repo.DownloadCallbacks):
    def mirror_failure(self, user_cb_data, msg, url):
        print("Mirror failure: ", msg)
        return 0


# Example implementation of transaction events callbacks
class TransactionCallbacks(libdnf5.rpm.TransactionCallbacks):
    def install_start(self, item, total):
        action_string = libdnf5.base.transaction.transaction_item_action_to_string(item.get_action())
        package_nevra = item.get_package().get_nevra()
        print(f'{action_string} started for package {package_nevra}')


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
