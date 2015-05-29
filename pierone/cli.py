import datetime
import os

import click

import requests
import yaml
from zign.api import get_named_token
from clickclick import error, AliasedGroup, print_table, OutputFormat

from .api import docker_login, request
import pierone


KEYRING_KEY = 'pierone'
CONFIG_DIR_PATH = click.get_app_dir('pierone')
CONFIG_FILE_PATH = os.path.join(CONFIG_DIR_PATH, 'pierone.yaml')

CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])

output_option = click.option('-o', '--output', type=click.Choice(['text', 'json', 'tsv']), default='text',
                             help='Use alternative output format')


def print_version(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    click.echo('Pier One CLI {}'.format(pierone.__version__))
    ctx.exit()


@click.group(cls=AliasedGroup, context_settings=CONTEXT_SETTINGS)
@click.option('--config-file', '-c', help='Use alternative configuration file',
              default=CONFIG_FILE_PATH, metavar='PATH')
@click.option('-V', '--version', is_flag=True, callback=print_version, expose_value=False, is_eager=True,
              help='Print the current version number and exit.')
@click.pass_context
def cli(ctx, config_file):
    path = os.path.expanduser(config_file)
    data = {}
    if os.path.exists(path):
        with open(path, 'rb') as fd:
            data = yaml.safe_load(fd)
    ctx.obj = data


@cli.command()
@click.option('--url', help='Pier One URL', metavar='URI')
@click.option('--realm', help='Use custom OAuth2 realm', metavar='NAME')
@click.option('-n', '--name', help='Custom token name (will be stored)', metavar='TOKEN_NAME', default='pierone')
@click.option('-U', '--user', help='Username to use for authentication', envvar='USER', metavar='NAME')
@click.option('-p', '--password', help='Password to use for authentication', envvar='PIERONE_PASSWORD', metavar='PWD')
@click.pass_obj
def login(obj, url, realm, name, user, password):
    '''Login to Pier One Docker registry (generates ~/.dockercfg'''
    try:
        with open(CONFIG_FILE_PATH) as fd:
            config = yaml.safe_load(fd)
    except:
        config = {}

    url = url or config.get('url')

    while not url:
        url = click.prompt('Please enter the Pier One URL')
        if not url.startswith('http'):
            url = 'https://{}'.format(url)

        try:
            requests.get(url, timeout=5)
        except:
            error('Could not reach {}'.format(url))
            url = None

        config['url'] = url

    os.makedirs(CONFIG_DIR_PATH, exist_ok=True)
    with open(CONFIG_FILE_PATH, 'w') as fd:
        yaml.dump(config, fd)

    docker_login(url, realm, name, user, password)


def get_token():
    try:
        token = get_named_token(['uid'], None, 'pierone', None, None)
    except:
        raise click.UsageError('No valid OAuth token named "pierone" found. Please use "pierone login".')
    return token


@cli.command()
@output_option
@click.pass_obj
def teams(config, output):
    '''List all teams having artifacts in Pier One'''
    token = get_token()

    r = request(config.get('url'), '/teams', token['access_token'])
    rows = [{'name': name} for name in sorted(r.json())]
    with OutputFormat(output):
        print_table(['name'], rows)


def get_artifacts(url, team, access_token):
    r = request(url, '/teams/{}/artifacts'.format(team), access_token)
    return r.json()

def get_tags(url, team, art, access_token):
    r = request(url, '/teams/{}/artifacts/{}/tags'.format(team, art), access_token)
    return r.json()

@cli.command()
@click.argument('team')
@output_option
@click.pass_obj
def artifacts(config, team, output):
    '''List all team artifacts'''
    token = get_token()

    result = get_artifacts(config.get('url'), team, token['access_token'])
    rows = [{'team': team, 'artifact': name} for name in sorted(result)]
    with OutputFormat(output):
        print_table(['team', 'artifact'], rows)


@cli.command()
@click.argument('team')
@click.argument('artifact', nargs=-1)
@output_option
@click.pass_obj
def tags(config, team, artifact, output):
    '''List all tags'''
    token = get_token()

    if not artifact:
        artifact = get_artifacts(config.get('url'), team, token['access_token'])

    rows = []
    for art in artifact:
        r = get_tags(config.get('url'), team, art, token['access_token'])
        rows.extend([{'team': team,
                      'artifact': art,
                      'tag': row['name'],
                      'created_by': row['created_by'],
                      'created_time': datetime.datetime.strptime(row['created'], '%Y-%m-%dT%H:%M:%S.%f%z').timestamp()}
                     for row in r])

    rows.sort(key=lambda row: (row['team'], row['artifact'], row['tag']))
    with OutputFormat(output):
        print_table(['team', 'artifact', 'tag', 'created_time', 'created_by'], rows,
                    titles={'created_time': 'Created', 'created_by': 'By'})


@cli.command()
@click.argument('team')
@click.argument('artifact')
@click.argument('tag', nargs=-1)
@output_option
@click.pass_obj
def scm(config, team, artifact, tag, output):
    '''Get scm information'''
    token = get_token()

    if not tag:
        tag = [t['name'] for t in get_tags(config.get('url'), team, artifact, token['access_token'])]

    rows = []
    for t in tag:
        row = request(config.get('url'), '/teams/{}/artifacts/{}/tags/{}/scm-source'.format(team, artifact, t), token['access_token']).json()
        rows.append({'tag': t,
                      'author': row['author'],
                      'created_time': datetime.datetime.strptime(row['created'], '%Y-%m-%dT%H:%M:%S.%f%z').timestamp(),
                      'revision': row['revision'],
                      'status': row['status']})

    rows.sort(key=lambda row: (row['tag'], row['created_time']))
    with OutputFormat(output):
        print_table(['tag', 'author', 'created_time', 'revision', 'status'], rows,
                    titles={'tag': 'Tag', 'author': 'By', 'created_time': 'Created', 'revision': 'Revision', 'status': 'Status'})

def main():
    cli()
