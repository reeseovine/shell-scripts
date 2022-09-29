#!/usr/bin/env python3

import pathlib as path
from subprocess import run
from subprocess import Popen

from time import sleep
from datetime import datetime

import argparse
import re
import json
import yaml
import pywal

from sunposition.sunposition import sunpos

from PIL import Image
from PIL import ImageFilter

from colors import draw
# from rgbctl import keeb

from pywalfox.channel.unix.client import Client
from pywalfox.config import COMMANDS


wallpapers_root = path.Path('/home/reese/Pictures/Wallpapers')
config_file = path.Path('/home/reese/.secrets/location.yml')
mode_file = path.Path('/home/reese/.cache/wal/light_mode')

### Find out whether it should use a light or dark theme based on the position of the sun.
def get_auto_mode():
	with open(config_file) as stream:
		config = yaml.safe_load(stream)
	if not (config['latitude'] and config['longitude'] and config['elevation']):
		print(f'Please put your location (latitude, longitude, and elevation) in {config_file} for auto mode to work!')
		return False
	sun = sunpos(dt=datetime.utcnow(), latitude=config['latitude'], longitude=config['longitude'], elevation=config['elevation'])
	angle = sun[1]
	if angle < 80:
		return 'light'
	return 'dark'

### Hang until the value returned by get_auto_mode() has changed, checking every `wait` seconds
def auto_wait(wait):
	initial = None
	with open(mode_file, 'r') as modefile:
		initial = ('dark','light')[modefile.read() == 'True']
	if initial is None:
		initial = get_auto_mode()

	new = initial
	while new == initial:
		sleep(wait)
		new = get_auto_mode()

	with open(mode_file, 'w') as modefile:
		modefile.write(str(new == 'light'))

	return new

### Get aspect ratio of current monitor setup.
def get_ratio_str():
	screens = run(
		['xrandr', '-q'],
		encoding='utf-8',
		capture_output=True
	).stdout
	resolution = re.search(r"current (\d+) x (\d+),", screens).group(1, 2)
	aspect_ratio = float(resolution[0]) / float(resolution[1])
	if aspect_ratio >= 2:
		return 'ultrawide'
	return 'normal'


### Generate blurred/tinted background for i3lock so it doesn't have to do it on-the-fly.
def gen_i3lock_bg(image, bgcolor):
	im = Image.open(image).filter(ImageFilter.GaussianBlur(radius=48))
	tint = Image.new(mode=im.mode, size=im.size, color=bgcolor)
	Image.blend(im, tint, 0.5).save('/tmp/i3lock_bg.png')

### Load color scheme from JSON file or, if it doesn't exist, generate one from the wallpaper.
def load_scheme(image, args):
	colors = None
	scheme_path = path.Path(f'/home/reese/.config/wal/colorschemes/{args.mode}/{path.Path(image).parts[-1]}.json')
	if scheme_path.is_file():
		with open(scheme_path) as scheme:
			return json.load(scheme)
	return pywal.colors.get(image, light=(args.mode == 'light'), backend=args.backend, sat=args.saturation)

### Tell various apps to reload their themes.
def update_apps(colors, image, args):
	pywal.reload.env()

	# change sway wallpaper
	# run(['swaymsg', 'output', '"*"', 'bg', image, 'fill'])

	# change GNOME wallpaper and appearance
	# run(['gsettings', 'set', 'org.gnome.desktop.background', 'picture-uri'+('-dark' if args.mode == 'dark' else ''), f'"file://{image}"'])
	# run(['gsettings', 'set', 'org.gnome.desktop.interface', 'color-scheme', f"'prefer-{args.mode}'"])

	gen_i3lock_bg(image, colors['colors']['color0'])

	# light/dark mode toggle for some applications
	run(['lightswitch', ('-l' if args.mode == 'light' else ''), '-t', 'sublime'])

	# (re)start dunst
	# run(['killall', 'dunst'])
	# Popen(['dunst',
	# '-lb', colors['special']['background'],
	# '-lf', colors['special']['foreground'],
	# '-nb', colors['special']['background'],
	# '-nf', colors['special']['foreground'],
	# '-cb', colors['colors']['color5'],
	# '-cf', '#ffffff'
	# ])

	# set laptop keyboard color
	# keeb(list(colors['colors'].values())[1:7])

	# update firefox and thunderbird themes
	client = Client()
	for host in client.hosts:
		connected = client.connect(host)
		if connected is True:
			client.send_message(COMMANDS['UPDATE'])
			if args.mode == 'dark':
				client.send_message(COMMANDS['THEME_MODE_DARK'])
			else:
				client.send_message(COMMANDS['THEME_MODE_LIGHT'])

	# compile discord theme
	# run(['sass', '/home/reese/git/github.com/reeseovine/discord-stuff/themes/bliss/pywal.scss', '/home/reese/git/github.com/reeseovine/discord-stuff/themes/bliss/pywal.css'])

	# trick eww into updating
	path.Path('/home/reese/.config/eww/eww.scss').touch()


def main(args):
	if args.mode == 'auto' or args.mode == 'auto_loop':
		args.mode = get_auto_mode()

	img_path = None
	if args.path:
		img_path = path.Path(args.path)
	else:
		ratio = get_ratio_str()
		img_path = wallpapers_root / ratio / args.mode

	image = pywal.image.get(str(img_path))
	colors = load_scheme(image, args)

	pywal.sequences.send(colors, vte_fix=True)
	pywal.export.every(colors)
	pywal.wallpaper.change(image)

	update_apps(colors, image, args)

	draw('small')


if __name__ == '__main__':
	parser = argparse.ArgumentParser(description='Set wallpaper and change color schemes of apps to match.')
	parser.add_argument('--mode', '-m', choices=['dark','light','auto','auto_loop'], default='auto')
	parser.add_argument('--backend', '-b', choices=['colorthief','fast_colorthief','colorz','haishoku','schemer2','wal'], default='colorz')
	parser.add_argument('--saturation', '-s', type=float, default=0.4)
	parser.add_argument('path', default='', nargs='?')
	args = parser.parse_args()

	if args.mode == 'auto_loop':
		while True:
			main(args)
			args.mode = auto_wait(300) # check every 5 minutes
	else:
		main(args)
