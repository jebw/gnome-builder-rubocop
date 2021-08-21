# Gnome-Builder plugin for Rubocop

Uses Rubocop to provide inline linting for ruby files in Gnome-Builder

## Install

```bash
mkdir -p ~/.local/share/gnome-builder/plugins
cd ~/.local/share/gnome-builder/plugins
git clone https://github.com/jebw/gnome-builder-rubocop.git rubocop
```

## Todo

* Check it works when no rubocop installed
* Check it works with system (as opposed to bundled) rubocop
* Check -1 offset is correct for rubocop output - taken from ESLint plugin
* Prefix copname if not already present
