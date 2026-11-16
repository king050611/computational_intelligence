import random
class Player:
    def __init__(self): self.rng=random.Random(19)
    def choose(self,board,pieces):
        moves=[]
        for r in range(9):
            for c in range(9):
                if board[r][c] not in pieces: continue
                for dr,dc in ((-1,0),(0,-1),(1,0),(0,1)):
                    nr,nc=r+dr,c+dc
                    while 0<=nr<9 and 0<=nc<9 and board[nr][nc] in (".","X"):
                        if board[nr][nc]==".": moves.append([[r,c],[nr,nc]])
                        nr,nc=nr+dr,nc+dc
        return self.rng.choice(moves)
    def play_attacker(self,board): return self.choose(board,"A")
    def play_defender(self,board): return self.choose(board,"DK")
