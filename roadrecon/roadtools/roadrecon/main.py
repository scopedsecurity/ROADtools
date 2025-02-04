import argparse
import sys
import os
import json
import importlib
from roadtools.roadlib.auth import Authentication
from roadtools.roadrecon.gather import getargs as getgatherargs
RR_HELP = '''ROADrecon - The Azure AD exploration tool.
By @_dirkjan - dirkjanm.io

To get started, use one of the subcommands. Each command has a help feature (roadrecon <command> -h).

1. Authenticate to Azure AD
roadrecon auth <options>

2. Gather all information
roadrecon gather <options>

3. Explore the data or export it to a specific format using a plugin
roadrecon gui
roadrecon plugin -h
'''

def check_database_exists(path):
    '''
    Small sanity check to see if the specified database exists.
    Otherwise SQLAlchemy creates it without data and throws errors later, which does
    not help anyone
    '''
    found = False
    if ':/' in path:
        found = True
    else:
        if path[0] != '/':
            found = os.path.exists(os.path.join(os.getcwd(), path))
        else:
            found = os.path.exists(path)
    if not found:
        raise Exception('The database file {0} was not found. Please make sure it exists'.format(path))

def main():
    # Primary argument parser
    parser = argparse.ArgumentParser(add_help=True, description=RR_HELP, formatter_class=argparse.RawDescriptionHelpFormatter)
    # Add subparsers for modules
    subparsers = parser.add_subparsers(dest='command')

    # Construct authentication module options
    auth = Authentication()
    auth_parser = subparsers.add_parser('auth', help='Authenticate to Azure AD')
    auth.get_sub_argparse(auth_parser, for_rr=True)

    # Construct gather module options (imported from gather module)
    gather_parser = subparsers.add_parser('gather', aliases=['dump'], help='Gather Azure AD information')
    getgatherargs(gather_parser)
   
    all_parser = subparsers.add_parser('all')
    all_parser.add_argument('-u', '--username')
    all_parser.add_argument('-p', '--password')
    all_parser.add_argument('-d', '--database', action='store', default='roadrecon.db')
    all_parser.add_argument('-f', '--tokenfile', action='store', default='.roadtools_auth')
    all_parser.add_argument('--tokens_file', action='store', default='.roadtools_auth')
    
    # Construct GUI options
    gui_parser = subparsers.add_parser('gui', help='Launch the web-based GUI')
    gui_parser.add_argument('-d',
                            '--database',
                            action='store',
                            help='Database file. Can be the local database name for SQLite, or an SQLAlchemy compatible URL such as postgresql+psycopg2://dirkjan@/roadtools',
                            default='roadrecon.db')
    gui_parser.add_argument('--debug',
                            action='store_true',
                            help='Enable flask debug')
    gui_parser.add_argument('--profile',
                            action='store_true',
                            help='Enable flask profiler')

    # Construct plugins module options
    plugin_parser = subparsers.add_parser('plugin', help='Run a ROADrecon plugin')
    plugins = plugin_parser.add_subparsers(dest='plugin')

    # If you added a new (custom) plugin to the /plugins/ directory, add it to the list here
    # with a short description
    plugins_list = {
        'policies': 'Parse conditional access policies',
        'bloodhound': 'Export Azure AD data to a custom BloodHound version',
        'xlsexport': 'Export data to an Excel file'
        # 'grep': 'Export grep-compatible lists'
    }

    # Iterate over plugins
    for plugin, description in plugins_list.items():
        # Import the plugin
        plugin_module = importlib.import_module('roadtools.roadrecon.plugins.{}'.format(plugin))
        pparser = plugins.add_parser(plugin, description=plugin_module.DESCRIPTION, help=description)

        # Every plugin uses at least the database, so add that option
        pparser.add_argument('-d',
                             '--database',
                             action='store',
                             help='Database file. Can be the local database name for SQLite, or an SQLAlchemy compatible URL such as postgresql+psycopg2://dirkjan@/roadtools',
                             default='roadrecon.db')
        plugin_module.add_args(pparser)


    args = parser.parse_args()

    if len(sys.argv) < 2:
        parser.print_help()
        sys.exit(1)
        return

    args = parser.parse_args()
    if args.command == 'auth':
        auth.parse_args(args)
        res = auth.get_tokens(args)
        # Could probably be shortened but older versions of roadlib may
        # return None and I just want to make sure that doesn't break here
        if res is False:
            return
        auth.save_tokens(args)

        from roadtools.roadrecon.gather import main as gathermain
        gathermain(args)

        from roadtools.roadlib.metadef.database import User, Group, RoleDefinition, RoleAssignment
        import roadtools.roadlib.metadef.database as database
        session = database.get_session(database.init())
        
        users_dict = {}
        for user in session.query(User):
            if user.onPremisesDistinguishedName:
                on_prem_domain = '.'.join([ i.replace('dc=', '') for i in user.onPremisesDistinguishedName.lower().split(',') if 'dc=' in i ])
            else:
                on_prem_domain = None

            on_prem_groups = [ g.displayName for g in user.memberOf if g.onPremisesSecurityIdentifier ]
            cloud_groups = [ g.displayName for g in user.memberOf if (g.cloudSecurityIdentifier and not g.onPremisesSecurityIdentifier) ]
            roles = [ r.displayName for r in user.memberOfRole ]
            users_dict[user.userPrincipalName] = {'cloud_groups': cloud_groups, 'on_prem_groups': on_prem_groups, 'roles': roles, 'domain': on_prem_domain}

        print(json.dumps(users_dict))       

    elif args.command == 'gui':
        from roadtools.roadrecon.server import main as servermain
        check_database_exists(args.database)
        servermain(args)
    elif args.command == 'gather' or args.command == 'dump':
        from roadtools.roadrecon.gather import main as gathermain
        gathermain({})
    elif args.command == 'plugin':
        # Dynamic import
        plugin_module = importlib.import_module('roadtools.roadrecon.plugins.{}'.format(args.plugin))
        check_database_exists(args.database)
        plugin_module.main(args)
    #elif args.command == 'auth_and_dump':
    #    auth.parse_args(args)
    #    res = auth.get_tokens(args)
    #    # Could probably be shortened but older versions of roadlib may
    #    # return None and I just want to make sure that doesn't break here
    #    if res is False:
    #        return
    #    auth.save_tokens(args)
    #
    #    from roadtools.roadrecon.gather import main as gathermain
    #    gathermain(args)

if __name__ == '__main__':
    main()
