import sys


def greet(name="thế giới"):
    return f"Xin chào, {name}!"


if __name__ == "__main__":
    print(greet(*sys.argv[1:2]))
