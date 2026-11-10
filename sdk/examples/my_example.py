import functools

def shout(func=None,*,mark="!"):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args,**kwargs):
            print(f"before{mark}")
            result = func(*args, **kwargs)
            print(f"after{mark}")
            return result
        return wrapper
    return decorator(func) if func is not None else decorator


@shout
def hello(name):
    return f"hi {name}"


@shout(mark="??")
def goodbye(name):
    return f"bye {name}"


if __name__ == "__main__":
    print(hello("sai"))
    print(goodbye("sai"))


    

