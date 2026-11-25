"""Tiny exhaustive test oracle, deliberately independent of production pruning."""
from src.game import apply_move,check_winner,get_legal_moves,get_state_key
from src.enhanced_search import WIN_SCORE,evaluate

def exact_score(board,side,root,depth,history=()):
    terminal=check_winner(board,side,history)
    if terminal:
        return 0 if terminal=="DRAW" else WIN_SCORE if terminal==root else -WIN_SCORE
    if depth==0:
        return evaluate(board,root)
    values=[exact_score(apply_move(board,m,side),"D" if side=="A" else "A",root,depth-1,history+(get_state_key(board,side),)) for m in get_legal_moves(board,side)]
    return (max if side==root else min)(values)
