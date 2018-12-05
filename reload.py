# Usage: reload.py <filename> <player_id> <bot_path> <optional_2nd_bot_path>

import json, subprocess, sys

try:
	import zstandard
	zstd_enabled = True
except:
	print("Couldn't import zstandard; therefore only .json can be opened, not .hlt")
	zstd_enabled = False


class Construct:
	def __init__(self, *, pid, sid, x, y, turn):
		self.pid = pid
		self.sid = sid
		self.x = x
		self.y = y
		self.turn = turn	# Turn the order to construct was given


class MoveList:

	# FIXME: currently assumes bot sends sane commands.

	def __init__(self, data):

		self.moves = dict()

		if type(data) is str:
			self.init_from_string(data)
		elif type(data) is list:
			self.init_from_list(data)
		else:
			raise TypeError


	def sids(self):

		ret = set()

		for key in self.moves:
			ret.add(key)

		return ret


	def init_from_string(self, s):		# i.e. from bot output

		tokens = s.split()

		command = None
		sid = None
		direction = None

		for token in tokens:

			if command == None:
				command = token
				if command == "g":
					self.moves["g"] = "g"
					command = None
				continue

			if sid == None:
				sid = int(token)
				if command == "c":
					self.moves[sid] = "c {}".format(sid)
					command = None
					sid = None
				continue

			direction = token
			self.moves[sid] = "m {} {}".format(sid, direction)

			command = None
			sid = None
			direction = None


	def init_from_list(self, lst):		# i.e. from replay

		for move in lst:

			if move["type"] == "g":
				self.moves["g"] = "g"

			elif move["type"] == "c":
				self.moves[move["id"]] = "c {}".format(move["id"])

			elif move["type"] == "m":
				self.moves[move["id"]] = "m {} {}".format(move["id"], move["direction"])


# ------------------------------

def send(link, msg):
	if msg.endswith("\n") == False:
		msg += "\n"
	msg = bytes(msg, encoding = "ascii")

	link.stdin.write(msg)
	link.stdin.flush()

# ------------------------------

class Game:

	def __init__(self, o):

		o["GAME_CONSTANTS"]["game_seed"] = o["map_generator_seed"]
		o["GAME_CONSTANTS"]["FACTOR_EXP_1"] = float(o["GAME_CONSTANTS"]["FACTOR_EXP_1"])
		o["GAME_CONSTANTS"]["FACTOR_EXP_2"] = float(o["GAME_CONSTANTS"]["FACTOR_EXP_2"])
		o["GAME_CONSTANTS"]["INSPIRED_BONUS_MULTIPLIER"] = float(o["GAME_CONSTANTS"]["INSPIRED_BONUS_MULTIPLIER"])
		self.game = o

		self.constructs = []

		for n, frame in enumerate(o["full_frames"]):

			events = frame["events"]

			for event in events:

				if event["type"] == "construct":

					c = Construct(
						pid = event["owner_id"],
						sid = event["id"],
						x = event["location"]["x"],
						y = event["location"]["y"],
						turn = n)

					self.constructs.append(c)


	def game_length(self):
		return len(self.game["full_frames"]) - 1

	def send_pregame(self, link, pid):

		o = self.game

		lines = []

		lines.append(json.dumps(o["GAME_CONSTANTS"], separators=(',', ':')))

		lines.append("{} {}".format(o["number_of_players"], pid))

		for p in o["players"]:

			lines.append("{} {} {}".format(
				p["player_id"],
				p["factory_location"]["x"],
				p["factory_location"]["y"],
			))

		lines.append("{} {}".format(o["production_map"]["width"], o["production_map"]["height"]))

		for y in range(o["production_map"]["height"]):
			tokens = [str(cell["energy"]) for cell in o["production_map"]["grid"][y]]
			lines.append(" ".join(tokens) + " ")	# Extra space at end of each line


		final = "\n".join(lines)
		send(link, final)

	def send_frame(self, link, n):		# n must be >= 1

		o = self.game

		lines = []

		this_frame = o["full_frames"][n]
		previous_frame = o["full_frames"][n - 1]

		lines.append(str(n))

		for pid in range(o["number_of_players"]):

			some_ships = this_frame["entities"][str(pid)]
			ship_count = len(some_ships)

			drop_count = 0

			for con in self.constructs:
				if con.pid == pid and con.turn < n:
					drop_count += 1

			budget = previous_frame["energy"][str(pid)]

			lines.append("{} {} {} {}".format(pid, ship_count, drop_count, budget))

			for sid, ent in some_ships.items():
				lines.append("{} {} {} {}".format(sid, ent["x"], ent["y"], ent["energy"]))

			for con in self.constructs:
				if con.pid == pid and con.turn < n:
					lines.append("{} {} {}".format(con.sid, con.x, con.y))

		cells = previous_frame["cells"]

		lines.append(str(len(cells)))

		for cell in cells:
			lines.append("{} {} {}".format(cell["x"], cell["y"], cell["production"]))


		final = "\n".join(lines)
		send(link, final)

# ------------------------------

def main():

	if len(sys.argv) < 4:
		print("Usage: reload.py <filename> <player_id> <bot_path> <optional_2nd_bot_path>")
		return

	filename = sys.argv[1]

	with open(filename, "rb") as infile:

		try:

			replay = json.loads(infile.read())

		except:

			infile.seek(0)

			if zstd_enabled == False:
				print("Run 'pip install zstandard' to read this file.")
				sys.exit()

			dctx = zstandard.ZstdDecompressor()
			compressed = infile.read()
			j = dctx.decompress(compressed)
			replay = json.loads(j)

	game = Game(replay)

	links = []

	for n in range(3, len(sys.argv)):
		links.append(subprocess.Popen(sys.argv[n], shell = False, stdin = subprocess.PIPE, stdout = subprocess.PIPE))

	pid = int(sys.argv[2])

	for link in links:
		game.send_pregame(link, pid)
		link.stdout.readline()

	bot_outputs = [ [] for n in range(len(links)) ]

	for lst in bot_outputs:
		lst.append(MoveList(""))	# No output for turn 0

	for n in range(1, game.game_length()):

		have_printed_turn = False

		for i, link in enumerate(links):
			game.send_frame(link, n)
			bot_outputs[i].append(MoveList(link.stdout.readline().decode("utf-8")))

		try:
			replay_moves = MoveList(game.game["full_frames"][n]["moves"][str(pid)])
		except KeyError:
			replay_moves = MoveList([])

		sids = replay_moves.sids()

		for i in range(len(links)):
			sids = sids.union(bot_outputs[i][n].sids())

		sids = list(sids)
		sids = sorted(sids, key = lambda sid: -1 if type(sid) is str else sid)

		for sid in sids:

			diverges = False
			baseline = replay_moves.moves.get(sid, "(blank)")

			for i in range(0, len(links)):
				other = bot_outputs[i][n].moves.get(sid, "(blank)")
				if other != baseline:
					diverges = True

			if diverges:

				if have_printed_turn == False:
					print("Turn {}".format(n))
					have_printed_turn = True

				messages = [baseline] + [bot_outputs[i][n].moves.get(sid, "(blank)") for i in range(len(bot_outputs))]

				print("    ", end="")

				for msg in messages:
					print(msg, end="")
					if len(msg) < 18:
						print(" " * (18 - len(msg)), end="")

				print()

# ------------------------------

main()
