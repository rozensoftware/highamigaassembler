#!/usr/bin/env python3
"""
Simple example: Generate a complete HAS program
"""

def main():
    code = """data constants:
    PI_APPROX = 3141592
    MAX_SIZE = 1024

code demo:
    proc add_numbers(d0:int, d1:int) -> int {
        var result:int = 0;
        result = d0;
        result += d1;
        return result;
    }
    
    proc main() -> int {
        var x:int = 10;
        var y:int = 20;
        var sum:int = 0;
        
        sum = x;
        sum += y;
        
        return sum;
    }
"""
    print(code)

if __name__ == "__main__":
    main()
