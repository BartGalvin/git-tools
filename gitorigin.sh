#!/usr/bin/env bash
set -euo pipefail

usage() {
    printf 'Usage: %s [OPTIONS] REPOSITORY_NAME\n' "${0##*/}"
    printf 'Create a bare repository over SSH and add it as the local origin. No push.\n'
    printf '  --host HOST          SSH host or SSH configuration alias\n'
    printf '  --user USER          SSH username\n'
    printf '  --directory PATH     Existing absolute repository directory on the server\n'
    printf '  --branch BRANCH      Initial branch (default: main)\n'
    printf '  --config FILE        Optional Git INI file; command-line values override it\n'
    printf '  --dry-run            Print the commands without SSH or local changes\n'
    printf 'Config keys: [remote] host, user, directory; [init] defaultBranch.\n'
    printf 'Host, user, and directory are required through options or config.\n'
}

host=
user=
directory=
branch=
config=
dry_run=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --host|--user|--directory|--branch|--config)
            if [[ $# -lt 2 || -z $2 ]]; then
                printf 'Error: %s requires a value.\n' "$1" >&2
                exit 2
            fi
            case "$1" in
                --host) host=$2 ;;
                --user) user=$2 ;;
                --directory) directory=$2 ;;
                --branch) branch=$2 ;;
                --config) config=$2 ;;
            esac
            shift 2
            ;;
        --dry-run) dry_run=true; shift ;;
        -h|--help) usage; exit 0 ;;
        --) shift; break ;;
        -*) printf 'Error: unknown option: %s\n' "$1" >&2; exit 2 ;;
        *) break ;;
    esac
done
if [[ $# -ne 1 ]]; then
    usage >&2
    exit 2
fi
if ! command -v git >/dev/null 2>&1; then
    printf 'Error: git is required.\n' >&2
    exit 1
fi
if [[ -n $config ]]; then
    if [[ ! -f $config || ! -r $config ]] ||
        ! git config --no-includes --file "$config" --list >/dev/null; then
        printf 'Error: config must be a readable Git INI file: %s\n' "$config" >&2
        exit 2
    fi
    [[ -n $host ]] || host=$(git config --no-includes --file "$config" --get remote.host || :)
    [[ -n $user ]] || user=$(git config --no-includes --file "$config" --get remote.user || :)
    [[ -n $directory ]] || directory=$(git config --no-includes --file "$config" --get remote.directory || :)
    [[ -n $branch ]] || branch=$(git config --no-includes --file "$config" --get init.defaultBranch || :)
fi
branch=${branch:-main}
if [[ ! $host =~ ^[A-Za-z0-9][A-Za-z0-9.-]*$ ]]; then
    printf 'Error: --host must be a hostname, IPv4 address, or SSH alias.\n' >&2
    exit 2
fi
if [[ ! $user =~ ^[A-Za-z_][A-Za-z0-9_.-]*$ ]]; then
    printf 'Error: --user must be an SSH username.\n' >&2
    exit 2
fi
if [[ $directory != /* || $directory == *[[:cntrl:]]* ]]; then
    printf 'Error: --directory must be an absolute path without control characters.\n' >&2
    exit 2
fi
name=$1
if [[ -z $name || $name == . || $name == .. || $name == -* ||
      $name == */* || $name == *[[:cntrl:]]* ]]; then
    printf 'Error: provide a repository name without slashes or control characters.\n' >&2
    exit 2
fi
if [[ $branch == '@{-'* ]] || ! git check-ref-format --branch "$branch" >/dev/null 2>&1; then
    printf 'Error: invalid branch name: %s\n' "$branch" >&2
    exit 2
fi
if ! git rev-parse --git-dir >/dev/null 2>&1; then
    printf 'Error: the current directory must be a Git repository.\n' >&2
    exit 1
fi
if git config --get-regexp '^remote\.origin\.' >/dev/null; then
    printf 'Error: origin already exists in the current repository.\n' >&2
    exit 1
fi

case "$name" in *.git) ;; *) name="$name.git" ;; esac
repository="${directory%/}/$name"
destination="$user@$host"
url="$destination:$repository"
# Git emits POSIX shell quoting, including for spaces and single quotes.
quoted_directory=$(git rev-parse --sq-quote "$directory")
quoted_repository=$(git rev-parse --sq-quote "$repository")
quoted_branch=$(git rev-parse --sq-quote "$branch")
printf -v remote_command '%s\n' \
    'set -eu' \
    "if [ ! -d$quoted_directory ]; then" \
    "    printf '%s\\n' 'Error: remote parent directory does not exist.' >&2" \
    '    exit 1' \
    'fi' \
    "if [ -e$quoted_repository ] || [ -L$quoted_repository ]; then" \
    "    printf '%s\\n' 'Error: remote destination already exists.' >&2" \
    '    exit 1' \
    'fi' \
    "mkdir --$quoted_repository" \
    "git init --bare --initial-branch$quoted_branch --$quoted_repository"

if "$dry_run"; then
    printf 'Would run: ssh'
    printf ' %q' -- "$destination" "$remote_command"
    printf '\nWould add origin: %s\n' "$url"
    exit 0
fi
if ! command -v ssh >/dev/null 2>&1; then
    printf 'Error: ssh is required.\n' >&2
    exit 1
fi
if ! ssh -- "$destination" "$remote_command"; then
    printf 'Error: remote initialization failed; origin was not added.\n' >&2
    exit 1
fi
if ! git remote add origin "$url"; then
    printf 'Error: origin could not be added; the remote bare repository remains: %s\n' "$url" >&2
    exit 1
fi
printf 'Created bare repository and added origin: %s\n' "$url"
