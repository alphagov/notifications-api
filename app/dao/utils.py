import random


def create_secret_code():
    return ''.join(map(str, random.sample(range(9), 5)))
