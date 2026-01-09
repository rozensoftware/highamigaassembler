# Quick Reference: Struct Pointers for robots.has

## Converting Your Existing Code

### Example: DrawBullets() Function

#### BEFORE (Current Code - Multiple Calculations)
```has
proc DrawBullets() -> void
{
    var bob_id:int;
    var i:int;
    var delay:byte;
    var x:word;
    var y:word;
    var frame:byte;

    for i = 0 to MAX_BULLETS
    {
        if (bullet[i].active == 1)
        {
            delay = bullet[i].anim_delay;    // Calculate bullet[i] address
            if (delay > 0)
            {
                delay = delay - 1;
                bullet[i].anim_delay = delay; // Calculate bullet[i] address AGAIN
            }
            else
            {
                bullet[i].anim_delay = ANIM_DELAY; // Calculate AGAIN
                frame = bullet[i].frame;            // Calculate AGAIN
                x = bullet[i].x;                    // Calculate AGAIN
                y = bullet[i].y;                    // Calculate AGAIN
                
                bob_id = i + 10;
                DrawBob(bob_id, x, y, frame);
                
                frame = frame + 1;
                if (frame >= BULLET_FRAMES) {
                    frame = 0;
                }
                bullet[i].frame = frame;             // Calculate AGAIN
            }
        }
    }
}
```

#### AFTER (With Struct Pointer - One Calculation)
```has
proc DrawBullets() -> void
{
    var bob_id:int;
    var i:int;
    var delay:byte;
    var x:word;
    var y:word;
    var frame:byte;
    var b:bullet*;    // <<< ADD THIS

    for i = 0 to MAX_BULLETS
    {
        b = &bullet[i];             // <<< CALCULATE ONCE
        if ((*b).active == 1)       // <<< USE POINTER
        {
            delay = (*b).anim_delay;
            if (delay > 0)
            {
                delay = delay - 1;
                (*b).anim_delay = delay;
            }
            else
            {
                (*b).anim_delay = ANIM_DELAY;
                frame = (*b).frame;
                x = (*b).x;
                y = (*b).y;
                
                bob_id = i + 10;
                DrawBob(bob_id, x, y, frame);
                
                frame = frame + 1;
                if (frame >= BULLET_FRAMES) {
                    frame = 0;
                }
                (*b).frame = frame;
            }
        }
    }
}
```

## Pattern to Apply

1. **Add pointer variable**:
   ```has
   var b:bullet*;
   ```

2. **Get address at start of loop**:
   ```has
   b = &bullet[i];
   ```

3. **Replace all `bullet[i]` with `(*b)`**:
   ```has
   bullet[i].active  →  (*b).active
   bullet[i].x       →  (*b).x
   bullet[i].frame   →  (*b).frame
   ```

## When to Use

✅ **USE when**:
- Inside loops
- Accessing 3+ fields of same struct
- Performance-critical code

❌ **DON'T USE when**:
- Single field access only
- One-time initialization code
- Simple setup functions

## Expected Performance Gain

For your robots.has game:
- **DrawBullets()**: ~40% fewer instructions in hot path
- **UpdateEnemies()**: Similar gains if you apply same pattern
- **Collision detection**: Big win if checking multiple fields

## Quick Search & Replace

To find all places where you access `bullet[i]` multiple times:

```bash
# Search for this pattern in your code:
grep "bullet\[i\]" robots.has
```

Any function with **3+ occurrences** of `bullet[i]` is a good candidate for optimization.

## Complete Example for Enemy Robots

```has
proc UpdateEnemies() -> void {
    var i:int;
    var e:Enemy*;    // Add pointer variable
    
    for i = 0 to MAX_ENEMY_ROBOTS {
        e = &enemies[i];              // Get address once
        
        if ((*e).active == 1) {
            // Update position
            (*e).x = (*e).x + (*e).dir_x;
            (*e).y = (*e).y + (*e).dir_y;
            
            // Update animation
            (*e).anim_delay = (*e).anim_delay - 1;
            if ((*e).anim_delay == 0) {
                (*e).frame = ((*e).frame + 1) & 3;
                (*e).anim_delay = ANIM_DELAY;
            }
            
            // Check bounds
            if ((*e).x < 0 || (*e).x > 320) {
                (*e).dir_x = -(*e).dir_x;
            }
        }
    }
}
```

## Common Mistakes to Avoid

### ❌ Wrong: Missing parentheses
```has
*p.field      // Parser error!
```

### ✓ Correct: Use parentheses
```has
(*p).field    // Works!
```

### ❌ Wrong: Don't get address multiple times
```has
for i = 0 to MAX_BULLETS {
    var b:bullet* = &bullet[i];    // Can't declare inside loop!
    (*b).x = 100;
}
```

### ✓ Correct: Declare once, assign in loop
```has
var b:bullet*;
for i = 0 to MAX_BULLETS {
    b = &bullet[i];                // Assign in loop
    (*b).x = 100;
}
```

## Testing Your Changes

After converting to pointers:

1. **Compile**: `make` - should work with no errors
2. **Compare output**: Verify game still works correctly
3. **Measure**: Run in emulator and check if it's faster

The generated assembly will be noticeably more efficient - check the `.s` file to see the difference!
