import os
import struct
import base58
from portalocker import Lock, unlock
import csv
import requests
import re

from solana.rpc.websocket_api import SolanaWsClientProtocol
from solana.rpc.commitment import Commitment

from solders.pubkey import Pubkey  # type: ignore
from solders.signature import Signature  # type: ignore
from solders.rpc.config import RpcTransactionLogsFilterMentions # type: ignore
from solders.rpc.responses import SubscriptionResult # type: ignore
from solders.rpc.config import RpcTransactionLogsFilterMentions # type: ignore
from solders.rpc.responses import RpcLogsResponse, SubscriptionResult, LogsNotification, GetTransactionResp # type: ignore
from solders.transaction_status import UiPartiallyDecodedInstruction, ParsedInstruction # type: ignore

from typing import AsyncIterator, List, Union
from pip._vendor.typing_extensions import Iterator

METADATA_PROGRAM_ID = "metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s"

def lock_file(file_path: str):
    lock_file_path = file_path + ".lock"
    lock = Lock(lock_file_path)
    lock.acquire()

def unlock_file(file_path: str):
    lock_file_path = file_path + ".lock"
    with open(lock_file_path, "a") as lock_file:
        unlock(lock_file)

def contains_word_from_list(symbol: str):
    ban_words = [
        "Dog", "Wif", "Hat", "Rico", 'SOL', "Toshi"
        "Trump", "Biden", "Putin", "SBF", "Cat", 'Pepe',
        "Brett", "Normie", "Test", "Help", "Hope", "MAGA",
        "Baby", "Shib", "Musk", "Elon", "Pink", "Ansem",
        "Mew", "Boden", "WALLY", "Garfield", "Bonk", "boden",
        "tremp", "Drake", "Meow", "May", "Grumpy", "Slurp"
    ]
    # Convert input_string to lowercase for case-insensitive comparison
    input_string_lower = symbol.lower()
    # Check if any word from the list is present in the input string
    for word in ban_words:
        if word.lower() in input_string_lower:
            return True
    return False

def save_token_address(data: dict, file_path: str):
    file_exists = os.path.isfile(file_path)

    with open(file_path, 'a') as file:
        writer = csv.DictWriter(file, fieldnames=data.keys())

        if not file_exists:
            writer.writeheader()

        writer.writerow(data)

def get_metadata_account(mint_key: Pubkey):
    return Pubkey.find_program_address(
        [b'metadata', bytes(Pubkey.from_string(METADATA_PROGRAM_ID)), bytes(mint_key)],
        Pubkey.from_string(METADATA_PROGRAM_ID)
    )[0]

def unpack_metadata_account(data, type_):
    assert(data[0] == 4)

    i = 1
    source_account = base58.b58encode(bytes(struct.unpack('<' + "B"*32, data[i:i+32])))
    i += 32
    mint_account = base58.b58encode(bytes(struct.unpack('<' + "B"*32, data[i:i+32])))
    i += 32
    name_len = struct.unpack('<I', data[i:i+4])[0]
    i += 4
    name = struct.unpack('<' + "B"*name_len, data[i:i+name_len])
    i += name_len
    symbol_len = struct.unpack('<I', data[i:i+4])[0]
    i += 4
    symbol = struct.unpack('<' + "B"*symbol_len, data[i:i+symbol_len])
    i += symbol_len
    uri_len = struct.unpack('<I', data[i:i+4])[0]
    i += 4
    uri = struct.unpack('<' + "B"*uri_len, data[i:i+uri_len])
    uri = bytes(uri).decode("utf-8").strip("\x00")

    data_ = requests.get(uri).json()

    # links = extract_links(data_.get('description', None))
    links = find_urls(data_.get('description', None))

    if type_ == 'raydium':
        metadata = {
        "symbol": bytes(symbol).decode("utf-8").strip("\x00"),
        "name": bytes(name).decode("utf-8").strip("\x00"),
        "isScam": "",
        "totalSupply": "",
        "creatorAddress": source_account.decode('utf-8'),
        "website": data_.get('website', links['website']),
        "telegram": data_.get('telegram', links['telegram']),
        "twitter": data_.get('twitter', links['twitter'])
    }
    elif type_ == 'pump.fun':
        metadata = {
        "symbol": bytes(symbol).decode("utf-8").strip("\x00"),
        "name": bytes(name).decode("utf-8").strip("\x00"),
        "website": data_.get('website', links['website']),
        "telegram": data_.get('telegram', links['telegram']),
        "twitter": data_.get('twitter', links['twitter'])
    }
    else:
        metadata = {}

    return metadata

def get_metadata(client, mint_key: Pubkey, type_):
    metadata_account = get_metadata_account(mint_key)
    try:
        data = client.get_account_info(metadata_account).value.data
        # print(data)
        # data = base64.b64decode(client.get_account_info(metadata_account).value.data)
        metadata = unpack_metadata_account(data, type_)
        return metadata
    except AttributeError as e:
        print('No metadata for', mint_key, ':', client.get_account_info(metadata_account))
        return None

def find_urls(string):
    links = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!.*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', string)
    telegram = find_item_with_substring(links, 't.me')
    if telegram in links:
        links.remove(telegram)
    twitter = find_item_with_substring(links, 'twitter')
    if twitter == None:
        twitter = find_item_with_substring(links, 'x.com')
    if twitter in links:
        links.remove(twitter)
    if len(links) > 0:
        website = links[-1]
    else:
        website = None
    return {'website': website, 'telegram': telegram if telegram else None, 'twitter': twitter if twitter else None}

def find_item_with_substring(lst, substring):
    matches = [item for item in lst if substring in item]
    return matches[0] if matches else None

def find_index_of_item_with_substring(lst, substring):
    matches = [i for i, item in enumerate(lst) if substring in item]
    return matches[0] if matches else -1

def extract_links(text):
    # Define patterns to match website, telegram, and twitter links
    patterns = {
        'website': r'Website:\s*(https?://\S+)',
        'telegram': r'Telegram:\s*(https?://\S+)',
        'twitter': r'Twitter:\s*(https?://\S+)'
    }

    # Initialize an empty dictionary to store the extracted links
    extracted_links = {}

    # Iterate through the patterns and extract the corresponding links
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if match:
            extracted_links[key] = match.group(1)

    return extracted_links

def get_pyth_solana_price():
    res = requests.get('https://hermes.pyth.network/v2/updates/price/latest?ids%5B%5D=0xef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d')
    data = res.json()['parsed'][0]['price']['price']
    price = int(data) / 10_000_0000
    return price

def get_msg_value(msg: List[LogsNotification]) -> RpcLogsResponse:
    return msg[0].result.value

def get_subscription_id(response: SubscriptionResult) -> int:
    return response[0].result

def get_instructions(
        transaction: GetTransactionResp
) -> List[Union[UiPartiallyDecodedInstruction, ParsedInstruction]]:
    return transaction \
        .value \
        .transaction \
        .transaction \
        .message \
        .instructions

def instructions_with_program_id(
        instructions: List[Union[UiPartiallyDecodedInstruction, ParsedInstruction]],
        program_id: Pubkey
) -> Iterator[Union[UiPartiallyDecodedInstruction, ParsedInstruction]]:
    return (instruction for instruction in instructions
            if instruction.program_id == program_id)

async def subscribe_to_logs(websocket: SolanaWsClientProtocol,
                            mentions: RpcTransactionLogsFilterMentions,
                            commitment: Commitment) -> int:
    await websocket.logs_subscribe(
        filter_=mentions,
        commitment=commitment
    )
    first_resp = await websocket.recv()
    return get_subscription_id(first_resp)  # type: ignore

async def process_messages(websocket: SolanaWsClientProtocol,
                           instruction: str) -> AsyncIterator[Signature]:
    """Async generator, main websocket's loop"""
    async for msg in websocket:
        value = get_msg_value(msg)
        for log in value.logs:
            if instruction not in log:
                continue
            yield value.signature