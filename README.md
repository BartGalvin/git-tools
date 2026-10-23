# Git tools

Two Bash scripts for creating bare Git repositories, locally or on an SSH
server. A bare repository stores Git history without a working copy, so it can
serve as a remote for your other repositories.

## Requirements

Bash 3.2 or later and Git 2.28 or later on macOS or Linux. For remote repositories,
you also need SSH access to a server with Git 2.28 or later installed.

Start in this project's directory for the configuration and local examples.

## Configuration

Copy the example configuration:

```sh
cp remote.example.conf remote.conf
```

Edit `remote.conf` with your server details and repository folders:

```ini
[remote]
    host = git.example.com
    user = gituser
    directory = /srv/git

[gbinit]
    directory = /path/to/local/repositories

[init]
    defaultBranch = main
```

Set `directory` under `[remote]` to a folder on your server, and under `[gbinit]`
to a folder on your computer. Use full paths to folders that already exist. You
only need the settings for the script you plan to use.

Both scripts use `main` by default. Change `defaultBranch` or pass `--branch NAME`
to choose another initial branch. Command-line options override the config.

## Create a local repository

Create a bare repository in the local folder from your config:

```sh
bash gbinit --config remote.conf example
```

This creates `/path/to/local/repositories/example.git`. The script adds `.git`
to the name if needed and stops if the destination already exists.

You can also give it a path without using a config:

```sh
bash gbinit /path/to/repos/example
```

## Set up a repository over SSH

`gitorigin.sh` creates a bare repository on your server and adds it as `origin`
in your local repository. From inside the local repository you want to connect,
preview the setup:

```sh
bash /path/to/git-tools/gitorigin.sh \
  --config /path/to/git-tools/remote.conf --dry-run example
```

Then run it without `--dry-run`:

```sh
bash /path/to/git-tools/gitorigin.sh \
  --config /path/to/git-tools/remote.conf example
```

With the config above, this creates `/srv/git/example.git` and sets `origin` to
`gituser@git.example.com:/srv/git/example.git`. It stops if `origin` or the remote
repository already exists. Push your commits with Git when you're ready.

Run either script with `--help` for the full list of options.
