import os
import asyncio
import websockets
import json
from solana.rpc.api import Client
from solders.pubkey import Pubkey  # type: ignore
from solders.signature import Signature  # type: ignore
import pandas as pd
from tabulate import tabulate
from datetime import datetime
from utils import contains_word_from_list, save_token_address
from definedfi import _getTokenInfo, _getPairMetadata
import requests

import logging
logger = logging.getLogger('websockets')
logger.setLevel(logging.ERROR)
logger.addHandler(logging.StreamHandler())

log_path = os.environ['LOG_PATH']
log_file_path = f"{log_path}/get_new_pool_{datetime.now().strftime('%Y-%m-%d')}.log"
unfiltered_data_path = os.environ['UNFILTERED_DATA_PATH']
filtered_data_path = os.environ['FILTERED_DATA_PATH']

wallet_address = os.environ['RAYDIUM_POOL_ADDRESS']
sol_address = os.environ['SOL_TOKEN_ADDRESS']
solana_client = Client(os.environ['SOLANA_RPC_CLIENT'])
websocket_client = os.environ['SOLANA_WEBSOCKET_CLIENT']
seen_signatures = set()

min_fdv = int(os.environ['MIN_FDV'])
max_fdv = int(os.environ['MAX_FDV'])
min_liq = int(os.environ['MIN_LIQ'])
min_mc_to_liq = float(os.environ['MIN_MC_TO_LIQ'])

rug_checker_url = os.environ['RUG_CHECKER_URL']

telegram_base_url = os.environ['TELEGRAM_BASE_URL']
telegram_bot_token = os.environ['TELEGRAM_BOT_TOKEN']
telegram_chat_id = os.environ['TELEGRAM_CHAT_ID']
    
logging.basicConfig(
    filename=log_file_path, 
    filemode='a', 
    datefmt='%Y-%m-%d %I:%M:%S %p',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

if os.path.isfile(log_file_path):
    print('Restarting...')
    logging.info('Restarting...')
else:
    print('Starting...')
    logging.info('Starting...')

REQUESTS = 0

def rugcheck(token_address: Pubkey):
    print('Inside rugcheck')
    url = rug_checker_url.replace('<token_address>', str(token_address))
    try:
        res = requests.get(url=url)
        if res.status_code == 200:
            data = res.json()
            if data and ('error' not in data.keys()):
                if ('risks' in data.keys()) and ('markets' in data.keys()) and (data['markets']) and (data['risks']):
                    lp_locked_perc = data['markets'][0]['lp']['lpLockedPct']
                    lp_locked = lp_locked_perc > 95
                    print(f'lpLocked percentage for {token_address}: {lp_locked_perc}%')
                    logging.info(f'lpLocked percentage for {token_address}: {lp_locked_perc}%')

                    risks = [risk['name'] for risk in data['risks']]
                    descriptions = [risk['description'] for risk in data['risks']]
                    top_10_high_ownership = True if 'Top 10 holders high ownership' in risks else False
                    mint_authorithy = True if 'Mint Authority still enabled' in risks else False
                    single_holder_ownership = True if 'Single holder ownership' in risks else False
                    high_ownership = True if 'High ownership' in risks else False
                    print(f'Risks for {token_address}: {descriptions}')

                    descriptions_to_str = ','.join(descriptions)
                    if mint_authorithy or not lp_locked:
                        return False, descriptions_to_str
                    return not (top_10_high_ownership and single_holder_ownership and high_ownership), descriptions_to_str
                else:
                    print(f'Markets information unavailable for {token_address}, skipping...')
                    logging.warning(f'Markets information unavailable for {token_address}, skipping...')
                    return False, ''
            else:
                print(f'Failed to find metadata for {token_address}, skipping...')
                logging.warning(f'Failed to find metadata for {token_address}, skipping...')
                return False, ''
        else:
            print(f'Failed to check if lp is locked for {token_address}')
            logging.warning(f'Failed to check if lp is locked for {token_address}')
            return False, ''
    except Exception as e:
        print(data)
        print(f'Rugcheck error:', e)
        exit(1)

# Sending contract address to a Telegram Channel
# The channel is continuously scaped by a trading bot
# The bot will parse the th contract address and auto buy the token
# Or just retrieve information about the token if auto buy is not activated
def send_contract_to_tg(token_address: Pubkey, data: dict):
    bot_token = telegram_bot_token
    chat_id = telegram_chat_id
    text = f"""
        ⏱️ timestamp: {data['timestamp']}
        📝 token_address: {token_address}
        💠 symbol: {data['symbol']}
        📛 name: {data['name']}
        💲 price: ${data['price']}
        💰 liquidity: {data['liquidity']}
        📈 fdv: {data['fdv']}
    """
    url = f'{telegram_base_url}/bot{bot_token}/sendMessage?chat_id={chat_id}&text={text}'

    res = requests.post(url=url)

    if res.status_code == 200:
        print('Token address sent to telegram for autobuy!')
    else:
        print('Failed to send token address to telegram for autobuy!', res.status_code)

async def getTokensWithBackoff(str_signature: str):
    retries = 6  # Maximum number of retries
    for i in range(retries):
        try:
            return await getTokens(str_signature)
        except Exception as e:
            print(f"Error: {e}. Retrying in {2**i} seconds...")
            await asyncio.sleep(2**i)
    raise Exception("Exceeded maximum retries. Unable to get tokens.")

async def getTokens(str_signature: str):
    global REQUESTS
    signature = Signature.from_string(str_signature)
    transaction = solana_client.get_transaction(
        signature, encoding="jsonParsed", max_supported_transaction_version=0).value
    instruction_list = transaction.transaction.transaction.message.instructions
    for instructions in instruction_list:
        if instructions.program_id == Pubkey.from_string(wallet_address):
            print("==================== NEW POOL DETECTED ====================")
            PairId = instructions.accounts[4]
            Token0 = instructions.accounts[8]
            Token1 = instructions.accounts[9]
            
            data = {'Token_Index': ['Token0', 'Token1', 'PairId'],
                    'Account Public Key': [Token0, Token1, PairId]}
            # df = pd.DataFrame(data)
            table = tabulate(data, headers='keys', tablefmt='fancy_grid')
            print(table)
            token_address = Token0 if str(Token0) not in sol_address else Token1
            # REQUESTS = REQUESTS + 1
            # print(f'Request #{REQUESTS}')
            # if REQUESTS % 5 == 0: # sleep to avoid rate limit for rug_checker
            #     await asyncio.sleep(1)
            # await asyncio.sleep(2) # sleep to avoid rate limits
            token_info = _getTokenInfo(token_address=str(token_address))
            print(f"{datetime.now().strftime('%I:%M:%S %p')} - Token Info for {token_address}: {token_info}")
            logging.info(f'Token Info for {token_address}: {token_info}')
            name_checks_out = contains_word_from_list(token_info['symbol'], token_info['name'])

            if not name_checks_out and len(token_info) > 0:
                now = datetime.now()
                today = now.strftime('%Y-%m-%d')
                result = {'timestamp': now, 'address': str(token_address)}
                result.update(token_info)
                quote_token = 'token0' if Token0 != wallet_address else 'token1'
                token_metadata = _getPairMetadata(pair_address=str(PairId), quote_token=quote_token)
                price = float(token_metadata['price']) if token_metadata['price'] else 0.0
                total_supply =  float(token_info['totalSupply']) if token_info['totalSupply'] else 0.0
                token_metadata['fdv'] = price * total_supply
                liquidity = float(token_metadata['liquidity']) if token_metadata['liquidity'] else 0.0
                result.update(token_metadata)

                print(f"{now.strftime('%I:%M:%S %p')} - Token Metadata for {token_address}: {token_metadata}")
                logging.info(f'Token Metadata for {token_address}: {token_metadata}')
                
                if  (min_fdv <= token_metadata['fdv']):
                    if (liquidity >= min_liq):
                        mc_to_liq = result['fdv'] / liquidity
                        if mc_to_liq >= min_mc_to_liq:
                            file_path = f'{unfiltered_data_path}/token_addresses_unfiltered_{today}.csv'
                            save_token_address(result, file_path)
                            logging.info(f"Token address {token_address} created at {now} and saved to token_address_unfiltered_{today}.csv")
                            print(f"Token address {token_address} created at {now} and saved to token_address_unfiltered_{today}.csv")
                            await asyncio.sleep(2)
                            check, risks = rugcheck(token_address=token_address)
                            result['risks'] = risks
                            if check:
                                file_path = f'{filtered_data_path}/token_addresses_filtered_{today}.csv'
                                save_token_address(result, file_path)
                                logging.info(f"Token address {token_address} created at {now} and saved to token_address_filtered_{today}.csv")
                                print(f"Token address {token_address} created at {now} and saved to token_address_filtered_{today}.csv")
                                send_contract_to_tg(token_address=token_address, data=result)
                            else:
                                logging.warning(f'Skipping {token_address} because lp is not locked')
                                print(f'Skipping {token_address} because lp is not locked')
                        else:
                            logging.warning(f"Skipping {token_address} because mc_to_liq={mc_to_liq} is too LOW")
                            print(f"Skipping {token_address} because mc_to_liq={mc_to_liq} is too LOW")
                    else:
                        logging.warning(f"Skipping {token_address} because liquidity={liquidity} is too LOW")
                        print(f"Skipping {token_address} because liquidity={liquidity} is too LOW")
                else:
                    # less_than_2000 = min_fdv >= token_metadata['fdv']
                    logging.warning(f"Skipping {token_address} because FDV={token_metadata['fdv']} is too LOW")
                    print(f"Skipping {token_address} because FDV={token_metadata['fdv']} is too LOW")

            break

async def run():
    async with websockets.connect(websocket_client, ping_interval=None) as websocket:
        try:
            # Send subscription request
            await websocket.send(json.dumps({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "logsSubscribe",
                "params": [
                    {"mentions": [wallet_address]},
                    {"commitment": "finalized"}
                ]
            }))
            first_resp = await websocket.recv()
            response_dict = json.loads(first_resp)
            if 'result' in response_dict:
                print("Subscription successful. Subscription ID:", response_dict['result'])
                logging.info(f"Subscription successful. Subscription ID: {response_dict['result']}")
            # Continuously read from the WebSocket
            async for response in websocket:
                response_dict = json.loads(response)
                if response_dict['params']['result']['value']['err'] is None:
                    signature = response_dict['params']['result']['value']['signature']
                    if signature not in seen_signatures:
                        seen_signatures.add(signature)
                        log_messages_set = set(response_dict['params']['result']['value']['logs'])
                        search = "initialize2"
                        if any(search in message for message in log_messages_set):
                            logging.info(f"Tx: https://solscan.io/tx/{signature}")
                            print(f"Tx: https://solscan.io/tx/{signature}")
                            await getTokensWithBackoff(signature)
                        else:
                            pass
            # await asyncio.sleep(1)
        except websockets.ConnectionClosed as e:
            logging.error(f'Terminated', e)
            print(f'Terminated', e)
        except Exception as e:
            logging.error(e)
            print(e)
        # TODO: Handle Keyboard Interrupt and CoonnectionCLosed Error
        # except (websockets.ProtocolError, websockets.ConnectionClosedError) as err:
        #     # Restart socket connection if ProtocolError: invalid status code
        #     logging.error(err)  # Logging
        #     print(f"Danger!", err)
        #     continue
        # except KeyboardInterrupt:
        #     if websocket:
        #         await websocket.logs_unsubscribe(subscription_id)

async def main():
    await run()

if __name__ == "__main__":
    asyncio.run(main())
