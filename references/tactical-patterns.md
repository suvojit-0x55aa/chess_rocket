# Tactical Patterns - Chess Speedrun Learning System

This guide covers essential tactical motifs that beginners must recognize and exploit. Each pattern is presented with recognition cues and teaching approaches for adaptive learning.

---

## 1. Forks

A fork is an attack on two or more opponent pieces simultaneously, forcing the loss of at least one piece.

### 1.1 Knight Fork

**Definition:** A knight moves to a square where it attacks two or more opponent pieces at once. The knight's unique L-shaped move makes it the most dangerous forking piece for beginners to overlook.

**Recognition Cues:**
- Look for opponent knights that can jump to squares controlling multiple pieces
- Common targets: king + rook, queen + rook, two minor pieces
- Knights on central squares (d4, e4, f5, etc.) are especially dangerous
- The knight fork is "unavoidable" - the king cannot defend other pieces

**Visual Pattern:**
```
A knight on d4 (or similar central square) attacks a piece on one square
(e.g., f5) and another piece on a different square (e.g., b3).
The pieces cannot both be defended by a single piece.
```

**Teaching Approach:**
- **Recognition drill:** Show positions where a knight fork is possible in 1-2 moves
- **Defensive lesson:** Teach avoiding knight fork opportunities (keep pieces away from knight-reachable squares)
- **Offensive lesson:** Identify squares where your knight can fork opponent pieces
- **Practice:** Present positions with knight move available; student must identify what pieces are under attack
- **Reinforcement:** "The knight's jump means it can attack two pieces that defend each other"

---

### 1.2 Queen Fork

**Definition:** The queen moves to a square where it attacks two or more opponent pieces simultaneously. Queens are the strongest forking piece due to their combination of sliding movement in all directions.

**Recognition Cues:**
- Look for lines (ranks, files, diagonals) where the queen can attack multiple pieces
- Often targets the king + a piece
- Happens most frequently after the opponent moves a piece onto a dangerous diagonal or line
- The queen can move from far away to create the fork (unlike the knight)

**Visual Pattern:**
```
A queen on a central diagonal attacks the opponent king on one square
and a bishop/rook on another square along the same diagonal.
Or a queen on a rank/file attacks multiple pieces in a line.
```

**Teaching Approach:**
- **Recognition drill:** Show queen positions that attack two pieces (even if pieces are defended)
- **Forcing moves:** Teach that queen forks are often possible after opponent makes mistakes
- **Defensive lesson:** "Don't put two pieces on the same line (rank, file, or diagonal) where the opponent's queen can reach"
- **Practice:** Multi-move sequences where you calculate queen forks 2-3 moves ahead
- **Reinforcement:** "Queens are powerful forking pieces - always check where your queen can move"

---

### 1.3 Pawn Fork

**Definition:** A pawn advances to a square where it attacks two opponent pieces simultaneously. This is the rarest fork but teaches piece placement discipline.

**Recognition Cues:**
- Look for positions where a pawn advance creates a diagonal attack on two pieces
- Typically happens in the endgame or when opponent's pieces are poorly placed
- The pawn fork is possible because pawns attack diagonally (different from their forward movement)
- Usually happens when opponent's pieces cluster on adjacent files and diagonals

**Visual Pattern:**
```
A pawn on e4 attacks pieces on d5 and f5 simultaneously.
A pawn advance from e3 to e4 creates the fork.
```

**Teaching Approach:**
- **Recognition drill:** Show positions with pawn advances creating forks
- **Piece placement:** "Avoid placing two pieces where a pawn advance could attack them both"
- **Offensive lesson:** Look for pawn advances that improve your position AND create threats
- **Practice:** Beginner positions where a single pawn push is devastating
- **Reinforcement:** "Pawns attack diagonally - that's where the danger is"

---

## 2. Pins

A pin is when a piece cannot move without exposing a more valuable piece (usually the king) to capture.

### 2.1 Absolute Pin

**Definition:** A piece is absolutely pinned when it cannot legally move without putting its own king in check. The pinned piece is completely immobilized.

**Recognition Cues:**
- Look for a line (rank, file, or diagonal) with: opponent's attacking piece → your piece → your king
- The pinned piece cannot move in ANY direction
- The pinning piece is usually a bishop, rook, or queen
- Most devastating pin type because the piece is completely helpless

**Visual Pattern:**
```
Opponent bishop on a2, your bishop on c4, your king on f1 (diagonal line).
Your bishop on c4 is absolutely pinned - it cannot move without exposing the king to check from the bishop.
```

**Teaching Approach:**
- **Recognition drill:** "Find the line that includes: enemy attacking piece, your piece, your king"
- **Immobility lesson:** "An absolutely pinned piece is frozen - act as if it doesn't exist for defense"
- **Tactical exploitation:** "Attack the pinned piece - your opponent cannot defend or move it"
- **Defensive strategy:** "Avoid positioning pieces in absolute pin situations"
- **Practice:** Positions where you must exploit an opponent's absolutely pinned piece
- **Reinforcement:** "Absolute pin = piece is locked in place and cannot defend anything"

---

### 2.2 Relative Pin

**Definition:** A piece is relatively pinned when moving it would expose a more valuable piece (but not the king) to capture. The piece CAN move legally, but doing so loses material.

**Recognition Cues:**
- Look for a line with: opponent's attacking piece → your piece → a more valuable piece (queen, rook, or bishop)
- The pinned piece has limited options - moving it usually loses material
- Less devastating than absolute pin (your king is safe), but still restricts piece activity
- The attacking piece can capture the more valuable piece if the pinned piece moves

**Visual Pattern:**
```
Opponent rook on a1, your rook on a4, your queen on a7 (all on the a-file).
Your rook on a4 is relatively pinned - if it moves, the opponent's rook captures your queen on a7.
```

**Teaching Approach:**
- **Recognition drill:** "Find the valuable piece behind the potentially pinned piece"
- **Trade evaluation:** "Is it worth trading/moving the pinned piece if we lose the piece behind it?"
- **Piece activity:** "Relative pins limit what your piece can do - use with caution"
- **Defensive wisdom:** "Sometimes moving a relatively pinned piece IS correct (if you gain enough material)"
- **Practice:** Positions where you decide whether to move a relatively pinned piece or leave it
- **Reinforcement:** "Relative pin limits options - weigh the consequences before moving"

---

## 3. Skewers

A skewer is the reverse of a pin: you attack a valuable piece, forcing it to move and exposing a less valuable piece behind it to capture.

**Definition:** The attacking piece targets a valuable enemy piece, which must move (or defend) to escape capture, leaving a less valuable piece behind it undefended and vulnerable to capture.

**Recognition Cues:**
- Look for a line with: your attacking piece → opponent's king or valuable piece → a less valuable piece
- The valuable piece MUST move (it's in check or directly attacked)
- After the valuable piece moves, you capture the less valuable piece
- Typically uses sliding pieces (bishops, rooks, queens) attacking along lines
- The first move is a check (skewer with check is most common)

**Visual Pattern:**
```
Your queen on e4, opponent king on e7, opponent rook on e9 (all on the e-file).
Your queen checks the king. The king must move. Then your queen captures the undefended rook.

OR (without check):
Your bishop on a2, opponent queen on c4, opponent bishop on e6 (on a diagonal).
Your bishop attacks the queen. The queen moves. Your bishop captures the bishop on e6.
```

**Teaching Approach:**
- **Recognition drill:** "Find a line where an opponent piece is attacked, and something valuable is behind it"
- **Forcing nature:** "The skewer forces the opponent to move the attacked piece"
- **Two-move sequence:** "Move 1: attack the piece. Move 2: capture what was behind it"
- **Offensive strategy:** "Look for opponent pieces lined up on a diagonal, rank, or file"
- **Practice:** Positions where you execute a skewer to win material
- **Reinforcement:** "Skewer = attacking the king or valuable piece to capture what's behind it"

---

## 4. Discovered Attacks

A discovered attack happens when moving one piece reveals an attack from another piece behind it.

**Definition:** Moving one piece uncovers a line of attack (rank, file, or diagonal) for another piece that was blocked by the moving piece. The moving piece and the revealed attacking piece both create threats.

**Recognition Cues:**
- Look for two pieces on the same line with opponent pieces beyond them
- The line is currently blocked by your moving piece
- Moving the front piece opens the line for the back piece to attack
- The moving piece can also create its own attack/threat
- Often involves: rook behind a minor piece, bishop behind a pawn, etc.

**Visual Pattern:**
```
Your rook on a1, your bishop on d1, opponent king on d8 (a-file and d-file align).
When you move the bishop from d1, it uncovers a discovered attack:
the rook on a1 now attacks pieces on the a-file, AND the bishop can move to create its own threats.
```

**Teaching Approach:**
- **Recognition drill:** "Find pieces on the same line with enemy pieces beyond them"
- **Double threat:** "The moving piece and the revealed piece both create threats"
- **Tactical power:** "Discovered attacks are powerful because you create two threats simultaneously"
- **Defensive awareness:** "Opponent can use discovered attacks against you too - watch for pieces aligned on lines"
- **Practice:** Positions where you move a piece to uncover a discovered attack
- **Reinforcement:** "Discovered attack = moving a piece reveals another piece's attack behind it"

---

## 5. Discovered Check

A discovered check happens when moving one piece reveals a check from another piece behind it.

**Definition:** A discovered check is a type of discovered attack where the revealed attack is specifically a check against the opponent's king. The moving piece may also give check (making it a double check).

**Recognition Cues:**
- Look for your piece on a line (rank, file, or diagonal) with the opponent king beyond it
- Your piece is currently blocking the line
- Moving your piece will put the opponent king in check from the piece behind it
- The moved piece may also create a check or other threat
- This is a forcing move (opponent MUST respond to the check)

**Visual Pattern:**
```
Your bishop on c4, your rook on a4, opponent king on a8 (all on the a-file).
When you move the bishop from c4 anywhere, it's a discovered check:
the rook on a4 now checks the king on a8 from the a-file.
```

**Teaching Approach:**
- **Recognition drill:** "Find YOUR piece between an ENEMY piece and the OPPONENT KING"
- **Forcing move:** "Moving your piece gives discovered check - the most forcing move possible"
- **Opponent response:** "Opponent must respond to check - they have no choice"
- **Offensive strategy:** "Look for discovered check opportunities to set up winning tactics"
- **Practice:** Positions where you move a piece to give discovered check and win material
- **Reinforcement:** "Discovered check forces opponent to respond - use it to gain advantage"

---

## 6. Double Check

A double check happens when moving a piece creates checks from BOTH the moved piece AND a revealed piece behind it.

**Definition:** Double check is the most forcing tactical blow. Moving a piece gives check AND reveals check from another piece behind it. The opponent king must move (it's the ONLY legal response to double check).

**Recognition Cues:**
- The moved piece itself gives check (e.g., knight move checking the king)
- Simultaneously, a piece behind the moved piece now checks the king
- Two checks at once = double check
- Opponent's ONLY legal response is to move the king (can't block two checks)
- This is the ultimate forcing move

**Visual Pattern:**
```
Your knight on e4, your rook on e1, opponent king on e8 (knight on e-file).
Move knight to f6 (checks king from the side AND discovers rook check from e-file).
Opponent king is in double check - MUST MOVE.
```

**Teaching Approach:**
- **Recognition drill:** "Can you move a piece to give check while also revealing check from behind?"
- **Ultimate forcing move:** "Double check forces opponent king to move - no other legal response exists"
- **King safety:** "After double check, opponent king is on the run - exploit its new position"
- **Win material/checkmate:** "Often sets up checkmate or winning material after the king moves"
- **Practice:** Positions where double check leads to checkmate or decisive material gain
- **Reinforcement:** "Double check is the most forcing tactical blow - opponent must move the king"

---

## 7. Back-Rank Threats

Back-rank threats involve checkmate patterns where a king on its starting rank (or trapped on the first/eighth rank) has no escape squares.

**Definition:** A back-rank mate occurs when an opponent king is on its starting rank (first rank for White, eighth rank for Black) with no escape squares, and your rook or queen delivers checkmate along that rank. The king is trapped because pawns in front of it block escape squares.

**Recognition Cues:**
- Opponent king is on the back rank (1st or 8th rank)
- The king's escape squares are blocked by its own pawns
- You have a rook or queen that can move to the king's rank and give checkmate
- Typically happens in the endgame when the king retreats
- The trapping pawns are usually on f-pawn, g-pawn, h-pawn (or a-pawn, b-pawn, c-pawn for Black)

**Visual Pattern:**
```
White king on h1, white pawns on f2, g2, h2 blocking escape.
Black rook can move to h1 (or the first rank) to give checkmate.
The king cannot escape left (g1 controlled by rook), right (edge of board), or up (blocked by pawns).
```

**Back-Rank Mate Patterns:**

1. **Simple Back-Rank Mate:** Rook on the back rank, king boxed in by pawns = checkmate

2. **Back-Rank with Escape Square:** If the king has one escape square, you may need to control it first

3. **Back-Rank Escape via Pawn Move:** Sometimes the trapped side can create an escape square by moving a pawn (e.g., h3 creates an escape on h2)

**Teaching Approach:**
- **Recognition drill:** "Find a king on the back rank with pawns in front - is it in danger?"
- **Defensive strategy:** "Keep an escape square for your king (e.g., h2 or h3 in the opening)"
- **Offensive strategy:** "Look for back-rank weaknesses in opponent's position"
- **Forcing moves:** "Back-rank threats are often the most forcing continuation - they lead to checkmate"
- **Prevention:** "Move a pawn to create an escape square (e.g., push h3 or f3 early)"
- **Practice:** Positions where you threaten or deliver back-rank mate
- **Reinforcement:** "Back-rank mate is a killer pattern - master it and use it against opponents"

---

## Teaching Integration

### Progressive Difficulty

**Beginner Level:**
- Recognize when a piece is hanging (undefended) = fork
- Identify absolute pins (piece locked in place)
- Simple back-rank weaknesses

**Intermediate Level:**
- Calculate multi-move tactics (discovered attack setting up a fork)
- Evaluate relative pins (decide whether to move)
- Create skewers and discovered attacks

**Advanced Level:**
- Double checks and discovered checks
- Complex tactical sequences combining multiple patterns
- Defensive tactics (creating counter-threats)

### Learning Approach

1. **Recognition first:** Show a tactic, ask student to identify the pattern
2. **Calculation next:** Given a position, calculate the sequence
3. **Creation last:** Given a position, find a move that creates the tactic

### Reinforcement

After each tactic is mastered:
- Present variations and defenses
- Show how opponents might prevent the tactic
- Teach the reverse (how to avoid letting opponent use this tactic against you)

---

## Summary Table

| Tactic | Pieces Involved | Key Idea | Forcer? |
|--------|-----------------|----------|---------|
| Knight Fork | Knight + 2+ pieces | Knight attacks multiple pieces | Yes |
| Queen Fork | Queen + 2+ pieces | Queen attacks multiple pieces | Yes |
| Pawn Fork | Pawn + 2 pieces | Pawn advance creates double attack | Yes |
| Absolute Pin | 3+ pieces in line | Pinned piece cannot move (check) | No |
| Relative Pin | 3+ pieces in line | Pinned piece loses material if moved | No |
| Skewer | 3+ pieces in line | Attack valuable piece to capture piece behind | Yes |
| Discovered Attack | 2 pieces + enemy piece | Moving one piece reveals another's attack | Yes |
| Discovered Check | 2+ pieces + enemy king | Moving one piece reveals check | Yes |
| Double Check | 2+ pieces + enemy king | Moving one piece creates TWO checks | Yes |
| Back-Rank Mate | Rook/Queen + trapped king | Checkmate on the back rank | Yes |

