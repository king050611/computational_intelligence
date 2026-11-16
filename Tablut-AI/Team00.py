# Tablut manual play example
# JC4004 Computational Intelligence 2025-26

class Player:
  
  # =================================================
  # Print the board
  @staticmethod
  def print_board(board):

    # Prints the current board
    print('')
    print('  0 1 2 3 4 5 6 7 8')
    for i in range(len(board)):
      txt = str(i) + ' '
      for j in range(len(board[i])):
        if board[i][j] == 'A':
          txt += "\033[34m" + board[i][j] + "\033[0m "
        elif board[i][j] == 'D':
          txt += "\033[33m" + board[i][j] + "\033[0m "
        elif board[i][j] == 'K':
          txt += "\033[93m" + board[i][j] + "\033[0m "
        else:
          txt += "\033[0;37m" + board[i][j] + "\033[0m "

      print(txt)
    print('')

  # =================================================
  # Play one move as a defender
  def play_defender(self, board):

    # First, print the current board
    self.print_board(board)

    # Get player input for new defender position
    print("Defender plays next!")

    defender_pos = [int(i) for i in input("Give the position where you want to move from (row,column): ").split(',')]
    move = [defender_pos]

    new_pos = [int(i) for i in input("Give the position where you want to move to (row,column): ").split(',')]
    move.append(new_pos)

    return move

  # =================================================
  # Play one move as a defender
  def play_attacker(self, board):

    # First, print the current board
    self.print_board(board)

    # Get player input for new defender position
    print("Attacker plays next!")

    attacker_pos = [int(i) for i in input("Give the position where you want to move from (row,column): ").split(',')]
    move = [attacker_pos]

    new_pos = [int(i) for i in input("Give the position where you want to move to (row,column): ").split(',')]
    move.append(new_pos)

    return move

# ==== End of file