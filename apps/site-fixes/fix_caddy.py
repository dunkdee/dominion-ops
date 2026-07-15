import sys

caddy_file = '/etc/caddy/Caddyfile'
with open(caddy_file) as f:
    content = f.read()

if 'surplus-public' in content:
    print('Caddy already updated')
    sys.exit(0)

old = 'surplus.dominionhealing.org {\n\treverse_proxy 127.0.0.1:8100\n}'
new = ('surplus.dominionhealing.org {\n'
       '\t@root_page {\n'
       '\t\tpath / /index.html\n'
       '\t}\n'
       '\thandle @root_page {\n'
       '\t\troot * /var/www/surplus-public\n'
       '\t\tfile_server\n'
       '\t}\n'
       '\thandle {\n'
       '\t\treverse_proxy 127.0.0.1:8100\n'
       '\t}\n'
       '}')

if old in content:
    content = content.replace(old, new)
    with open(caddy_file, 'w') as f:
        f.write(content)
    print('Surplus Caddy block updated')
else:
    print('WARNING: pattern not found in Caddyfile - check manually')
    sys.exit(1)
