# Tablut testing framework
# JC4004 Computational Intelligence 2026-27

import copy, time, random

# Define time limit
TIME_BUDGET = 60.0  # Max. 60 seconds total playing time per player
ZOBRIST_SEED = 42

class Tablut:

  # =================================================
  # Initialise the board for a new game
  def __init__(self):

    # Initialise a new game
    self.board = [
      ['.', '.', '.', 'A', 'A', 'A', '.','.','.'],
      ['.', '.', '.', '.', 'A', '.', '.','.','.'],
      ['.', '.', '.', '.', 'D', '.', '.','.','.'],
      ['A', '.', '.', '.', 'D', '.', '.','.','A'],
      ['A', 'A', 'D', 'D', 'K', 'D', 'D','A','A'],
      ['A', '.', '.', '.', 'D', '.', '.','.','A'],
      ['.', '.', '.', '.', 'D', '.', '.','.','.'],
      ['.', '.', '.', '.', 'A', '.', '.','.','.'],
      ['.', '.', '.', 'A', 'A', 'A', '.','.','.']
    ]
    self.rounds_played = 0
    self.winner = None

    random.seed(ZOBRIST_SEED)
    self.zobrist_hash_table = {
      square: {
        piece: {
          turn: random.getrandbits(64) for turn in range(2)
        }
        for piece in range(3)
      }
      for square in range(len(self.board) ** 2)
    }
    self.past_positions = []

  # =================================================
  # Compute Zobrist hash for the board position
  def compute_zobrist_hash(self, attackers_turn: bool = True):

    new_hash = 0
    turn = 0 if attackers_turn else 1
    for i in range(len(self.board)):
      for j in range(len(self.board[i])):
        if self.board[i][j] == 'A':
          new_hash ^= self.zobrist_hash_table[i * len(self.board) + j][0][turn]
        elif self.board[i][j] == 'D':
            new_hash ^= self.zobrist_hash_table[i * len(self.board) + j][1][turn]
        elif self.board[i][j] == 'K':
            new_hash ^= self.zobrist_hash_table[i * len(self.board) + j][2][turn]

    return new_hash

  # =================================================
  # Test if there is a legal capture
  def test_captures(self, row, col, new_board):

    # Test for capture
    dir_row = [-1,0,1,0]
    dir_col = [0,-1,0,1]
    for i in range(4):

      if not (0 <= row + dir_row[i] * 2 < len(self.board) and 0 <= col + dir_col[i] * 2 < len(self.board)):
        continue

      # Case 1: Defender or King captures attacker
      if new_board[row][col] in ['D','K']:
        if new_board[row + dir_row[i]][col + dir_col[i]] == 'A':
          if new_board[row + dir_row[i] * 2][col + dir_col[i] * 2] in ['D','K','X']:
            new_board[row + dir_row[i]][col + dir_col[i]] = '.'

      # Case 2: Attacker captures Defender
      if new_board[row][col] == 'A':
        if new_board[row + dir_row[i]][col + dir_col[i]] == 'D':
          if new_board[row + dir_row[i] * 2][col + dir_col[i] * 2] in ['A','X']:
            new_board[row + dir_row[i]][col + dir_col[i]] = '.'

          # Special case: King in the castle and surrounded by three attackers
          elif new_board[row + dir_row[i] * 2][col + dir_col[i] * 2] == 'K' and \
              row + dir_row[i] * 2 == 4 and col + dir_col[i] * 2 == 4:
            num_surrounding = 0
            for j in range(4):
              if new_board[4 + dir_row[j]][4 + dir_col[j]] == 'A':
                num_surrounding += 1
              if num_surrounding == 3:
                new_board[row + dir_row[i]][col + dir_col[i]] = '.'

        # Case 3: Attacker captures King
        elif new_board[row + dir_row[i]][col + dir_col[i]] == 'K':

          # King is not in the castle and not besides the castle: capture normally
          if not (row + dir_row[i] == 4 and 2 < col + dir_col[i] < 6) and \
                  not (col + dir_col[i] == 4 and 2 < row + dir_row[i] < 6):
            if new_board[row + dir_row[i] * 2][col + dir_col[i] * 2] == 'A':
              new_board[row + dir_row[i]][col + dir_col[i]] = '.'

          # King is in the castle or besides it: must be surrounded from all directions
          else:
            num_surrounding = 0
            for j in range(4):
              if new_board[row + dir_row[i] + dir_row[j]] \
                          [col + dir_col[i] + dir_col[j]] in ['A','X']:
                num_surrounding += 1
            if num_surrounding == 4:
              new_board[row + dir_row[i]][col + dir_col[i]] = '.'

    return new_board


  # =================================================
  # Check if the move is valid and update the board
  def make_move(self, is_attacker, moves):

    # Round is counted even if the move is illegal
    self.rounds_played += 1

    # Test for valid number of moves and value of staring position
    if len(moves) != 2 or len(moves[0]) != 2 or len(moves[1]) != 2:
      return False

    start_row, start_col = moves[0][0], moves[0][1]
    end_row, end_col = moves[1][0], moves[1][1]

    if not (0 <= start_row < len(self.board)) or not (0 <= start_col < len(self.board)) \
         or not (0 <= end_row < len(self.board)) or not (0 <= end_col < len(self.board)):
      return False
    elif self.board[start_row][start_col] != 'A' and is_attacker:
      return False
    elif not is_attacker:
      if self.board[start_row][start_col] not in ['D','K']:
        return False

    # Test if ending position is empty
    if self.board[end_row][end_col] != '.':
        return False

    # Test if proper orthogonal moving with no obstacles
    if start_row == end_row:
      for i in range(min(start_col,end_col) + 1, max(start_col,end_col)):
        if self.board[start_row][i] not in ['.','X']:
          return False
    elif start_col == end_col:
      for i in range(min(start_row,end_row) + 1, max(start_row,end_row)):
        if self.board[i][start_col] not in ['.','X']:
          return False
    else:
      return False

    # Initialise new board
    new_board = copy.deepcopy(self.board)

    # Legal move(s): update the board
    if start_row == 4 and start_col == 4:
      new_board[start_row][start_col] = 'X'
    else:
      new_board[start_row][start_col] = '.'

    new_board[end_row][end_col] = self.board[start_row][start_col]

    # Test for captures
    new_board = self.test_captures(end_row, end_col, new_board)

    self.board = new_board
    return True

  # =================================================
  # Check if the game is won by one player
  def check_if_game_over(self, is_attacker_next):

    # Find positions for pieces
    attacker_pos = []
    defender_pos = []
    king_found = False
    for i in range(len(self.board)):
      for j in range(len(self.board[i])):
        if self.board[i][j] == 'K':

          # If King reached the edge, defenders have won
          if i in [0, len(self.board)-1] or j in [0, len(self.board[i])-1]:
            self.winner = 'D'
            return True

          king_found = True
          defender_pos.append([i, j])

        # Update attacker positions
        elif self.board[i][j] == 'A':
          attacker_pos.append([i,j])

        # Update defender positions
        elif self.board[i][j] == 'D':
          defender_pos.append([i, j])

    # If no King, attackers have won
    if not king_found:
      self.winner = 'A'
      return True

    # If less than two Attackers, Defenders have won
    if len(attacker_pos) < 2:
      self.winner = 'D'
      return True

    # Check if there are legal moves
    check_pos = attacker_pos if is_attacker_next else defender_pos
    dir_row = [-1,0,1,0]
    dir_col = [0,-1,0,1]
    legal_move_found = False
    for pos in check_pos:
      for i in range(4):

        # Test if in the area
        if not (0 <= pos[0]+dir_row[i] < len(self.board) and 0 <= pos[1]+dir_col[i] < len(self.board)):
          continue

        # If the adjacent position is empty, there is at least one legal move
        if self.board[pos[0]+dir_row[i]][pos[1]+dir_col[i]] == '.':
          legal_move_found = True

        # If the adjacent position is castle, we need to check also the other side of the castle
        elif self.board[pos[0]+dir_row[i]][pos[1]+dir_col[i]] == 'X':
          if self.board[pos[0]+dir_row[i]*2][pos[1]+dir_col[i]*2] == '.':
            legal_move_found = True

    if not legal_move_found:
      print("Player cannot move")
      self.winner = None
      return True

    # Finally, check if the position is repeating
    hash = self.compute_zobrist_hash(is_attacker_next)
    if hash in self.past_positions:
      print("Repeated position found")
      self.winner = None
      return True

    self.past_positions.append(hash)

    # Game is not over yet
    return False

  # =================================================
  # Play one round of the game between players 1 (attacker) and 2 (defender)
  def play(self, attacker_player, defender_player):

    # Initialise
    game_over = False
    rounds_played = 0
    attacker_time = TIME_BUDGET
    defender_time = TIME_BUDGET
    self.past_positions = [self.compute_zobrist_hash(True)]

    # Play a round of the game
    while not game_over:

      # The attacker plays first
      temp_board = copy.deepcopy(self.board)
      start_time = time.time()
      try:
        move = attacker_player.play_attacker(temp_board)
      except Exception as err:
        print("Exception caught for Attackers!")
        self.winner = 'D'
        game_over = True
      else:
        attacker_time -= time.time() - start_time
        if attacker_time < 0:
          print("Attackers exceeded time limit!")
          self.winner = 'D'
          game_over = True
        elif not self.make_move(True, move):
          print("Illegal move by Attackers!")
          self.winner = 'D'
          game_over = True
        else:
          game_over = self.check_if_game_over(False)

      if not game_over:

        # The defender plays second
        temp_board = copy.deepcopy(self.board)
        start_time = time.time()
        try:
          move = defender_player.play_defender(temp_board)
        except Exception as err:
          print("Exception caught for Defenders!")
          self.winner = 'A'
          game_over = True
        else:
          defender_time -= time.time() - start_time
          if defender_time < 0: # This will 10 when testing the bots
            print("Defenders exceeded time limit!")
            self.winner = 'A'
            game_over = True
          elif not self.make_move(False, move):
            print("Illegal move by Defenders!")
            self.winner = 'A'
            game_over = True
          else:
            game_over = self.check_if_game_over(True)

      rounds_played += 1

    # Game is over
    if self.winner == 'A':
      print("Game over, Attackers won!")
    elif self.winner == 'D':
      print("Game over, Defenders won!")
    else:
      print("Game over, it is draw, no winner!")

    print("Rounds played: " + str(rounds_played))

# ===================================================
# The main function demonstrates how to run a game
if __name__ == "__main__":
  # Init the game
  game = Tablut()

  # Import the players
  module = __import__("Team00") # Rebel bot module
  rebel = getattr(module, "Player")()
  module = __import__("Team00") # Officer bot module
  officer = getattr(module, "Player")()

  # Play the game
  game.play(rebel, officer)

# ==== End of file