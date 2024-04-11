import os
from portalocker import Lock, unlock
import csv

def lock_file(file_path: str):
    lock_file_path = file_path + ".lock"
    lock = Lock(lock_file_path)
    lock.acquire()

def unlock_file(file_path: str):
    lock_file_path = file_path + ".lock"
    with open(lock_file_path, "a") as lock_file:
        unlock(lock_file)

def contains_word_from_list(symbol: str, name: str):
    # if name == symbol:
    #     return False
    
    # ban_words = [
    #     "Dog", "Wif", "Hat", "Rico", 'SOL', "Toshi"
    #     "Trump", "Biden", "Putin", "SBF", "Cat", 'Pepe',
    #     "Brett", "Normie", "Test", "Help", "Hope", "MAGA",
    #     "Baby", "Shib", "Musk", "Elon", "Pink", "Ansem",
    #     "Mew", "Boden", "WALLY", "Garfield", "Bonk", "boden",
    #     "tremp", "Drake", "Meow", "May", "Grumpy", "Slurp"
    # ]
    # # Convert input_string to lowercase for case-insensitive comparison
    # input_string_lower = symbol.lower()
    # # Check if any word from the list is present in the input string
    # for word in ban_words:
    #     if word.lower() in input_string_lower:
    #         return True
    return False

def save_token_address(data, file_path):
    file_exists = os.path.isfile(file_path)

    with open(file_path, 'a') as file:
        writer = csv.DictWriter(file, fieldnames=data.keys())

        if not file_exists:
            writer.writeheader()

        writer.writerow(data)