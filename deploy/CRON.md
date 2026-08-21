# The one cron job this site needs

Set this up once, after deploying. Nothing else on this site needs a schedule.

```
0 3 * * * cd /home/ACCOUNT/salon && /home/ACCOUNT/virtualenv/salon/3.12/bin/python manage.py maintenance
```

In cPanel: **Advanced → Cron Jobs → Add New Cron Job**, "Once Per Day (0 3 * * *)".

Replace `ACCOUNT` with your cPanel username and check the two paths against your
own account — see *Getting the paths right* below, because a wrong path here is
the single most common reason a cron job silently never runs.

---

## What it does

| Step | Why it has to happen |
|---|---|
| Purge expired sessions | Django never does this itself. The docs are explicit that it is the operator's job. `django_session` otherwise grows for the life of the site. |
| Prune the admin log | `django_admin_log` records every admin change and also grows forever. Default retention is a year. |
| Take a backup | The database and the payment screenshots are the only two things that cannot be rebuilt from the repository. Keeps the last 14. |
| Check email is configured | The failure this exists to catch: bookings save fine, notifications silently stop, and it looks like a quiet week. |

## What it prints

**Nothing, when everything worked.** That is deliberate. cPanel emails you
whatever a cron job prints, and a job that reports five cheerful lines every
night teaches you to filter the address — so the one night it has something to
say is the night you do not read it.

A failure prints every step, succeeded and failed, and exits non-zero. That is
what makes the email arrive.

Note that email goes through **cPanel's own mail system**, not through this
application's SMTP settings. So it still reaches you on the day the thing that
broke is the application's email.

To see what it actually does, run it by hand:

```
python manage.py maintenance -v 2
```

## Getting the paths right

Cron runs with almost no environment: no virtualenv, no `PATH`, not even the
right working directory. Both paths must be absolute.

Find them on the server:

```
# the python inside your cPanel virtualenv
which python          # after running the venv's activation command
# the project directory (where manage.py is)
pwd
```

cPanel shows the activation command on **Setup Python App**. It looks like
`source /home/ACCOUNT/virtualenv/salon/3.12/bin/activate` — the python you want
is that same directory with `/python` instead of `/activate`.

## Checking it is working

After the first night:

```
ls -la backups/          # a dated file should have appeared
tail logs/salon.log      # warnings and errors land here
```

If nothing appeared and you got no email, the cron job did not run at all —
almost always a wrong path. Test the exact command by pasting it into SSH; it
should complete silently and exit 0.

## Options

| Flag | Default | |
|---|---|---|
| `--keep-days N` | 365 | Days of admin history to keep. `0` disables pruning. |
| `--backup-keep N` | 14 | How many backups to retain. |
| `--backup-dir PATH` | `backups/` | Put this outside `public_html`. |
| `--no-backup` | | Skip the backup, if something else already takes one. |
| `-v 2` | | Print what each step did. |

## One thing to keep an eye on

Backups accumulate at roughly the size of your database plus any locally-stored
payment screenshots, times 14. On a shared hosting quota that is worth checking
after the first fortnight — `du -sh backups/`. Lower `--backup-keep` if it is
larger than you expected.
