#!/usr/bin/env python

import os
import asyncio
from websockets.exceptions import ConnectionClosedError, ProtocolError, ConnectionClosed

from solana.rpc.api import Client
from solana.rpc.websocket_api import connect
from solana.rpc.commitment import Finalized

from solders.pubkey import Pubkey  # type: ignore
from solders.signature import Signature  # type: ignore
from solders.rpc.config import RpcTransactionLogsFilterMentions # type: ignore
from solders.rpc.responses import GetTransactionResp # type: ignore

from tabulate import tabulate
from datetime import datetime
from utils import contains_word_from_list, save_token_address, subscribe_to_logs, get_metadata, process_messages, instructions_with_program_id, get_pyth_solana_price
from definedfi import _getTokenInfo, _getPairMetadata
import requests
import ssl

import logging
logger = logging.getLogger('websockets')
logger.setLevel(logging.ERROR)
logger.addHandler(logging.StreamHandler())

log_path = os.environ['LOG_PATH']
log_file_path = f"{log_path}/sol-listener/get_new_pool_{datetime.now().strftime('%Y-%m-%d')}.log"
unfiltered_data_path = os.environ['UNFILTERED_DATA_PATH']
filtered_data_path = os.environ['FILTERED_DATA_PATH']

RaydiumLPV4 = os.environ['RAYDIUM_POOL_ADDRESS']
TOKEN_PROGRAM_ID = Pubkey.from_string('TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA')
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

log_instruction = "initialize2"
    
logging.basicConfig(
    filename=log_file_path, 
    filemode='a', 
    datefmt='%Y-%m-%d %I:%M:%S %p',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def get_token_supply(
        transaction: GetTransactionResp
) -> int:
    
    inner_instructions = transaction \
        .value \
        .transaction \
        .meta \
        .inner_instructions
    
    for instruction in inner_instructions:
        filtered_instructions = instructions_with_program_id(instruction.instructions, TOKEN_PROGRAM_ID)
        for filtered_instruction in filtered_instructions:
            if filtered_instruction.parsed['type'] == 'mintTo':
                return filtered_instruction.parsed['info']['amount']
    return 0        

def rugcheck(token_address: Pubkey):
    print('Inside rugcheck')
    url = rug_checker_url.replace('<token_address>', str(token_address))
    try:
        res = requests.get(url=url)
        if res.status_code == 200:
            data: dict = res.json()
            if data and ('error' not in data.keys()):
                if ('risks' in data.keys()) and ('topHolders' in data.keys()):
                    # lp_locked_perc = data['markets'][0]['lp']['lpLockedPct']
                    # lp_locked = lp_locked_perc > 95
                    # print(f'lpLocked percentage for {token_address}: {lp_locked_perc}%')
                    # logging.info(f'lpLocked percentage for {token_address}: {lp_locked_perc}%')

                    risks = [risk['name'] for risk in data['risks']]
                    descriptions = [risk['description'] for risk in data['risks']]
                    mint_authorithy = True if 'Mint Authority still enabled' in risks else False
                    print(f'Risks for {token_address}: {descriptions}')

                    top_holders = data['topHolders']
                    top_holders_supply_pct = 0
                    top_holders_addresses_with_supply = []
                    for i in range(len(top_holders)):
                        top_holders_addresses_with_supply.append(f"{top_holders[i]['owner']} - {top_holders[i]['pct']} %")
                        if top_holders[i]['owner'] not in ['5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1', '11111111111111111111111111111111']:
                            top_holders_supply_pct += top_holders[i]['pct']
                    
                    descriptions_to_str = ', '.join(descriptions)

                    # if mint_authorithy:
                    #     return False, '', None, ''

                    return True, descriptions_to_str, top_holders_supply_pct, ', '.join(top_holders_addresses_with_supply)
                else:
                    print(f'Risks/top holders information unavailable for {token_address}, skipping...')
                    logging.warning(f'Risks/top holders information unavailable for {token_address}, skipping...')
                    return False, '', None, ''
            else:
                print(f'Failed to find metadata for {token_address}, skipping...')
                logging.warning(f'Failed to find metadata for {token_address}, skipping...')
                return False, '', None
        else:
            print(f'Rugcheck API call failed for {token_address} | code: {res.status_code}')
            logging.warning(f'Rugcheck API call failed for {token_address} | code: {res.status_code}')
            return False, '', None
    except Exception as e:
        print(data)
        print(f'Rugcheck error:', e)

# Sending contract address to a Telegram Channel
# The channel is continuously scraped by a trading bot
# The bot will parse the contract address and auto buy the token
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
        ⚠️ risks: {data['risks']}
        🤝 dexscreener: https://dexscreener.com/solana/{token_address}
        🗃️ top20 holders supply (excluding pool): {data['topHoldersSupplyPct']}
        👥 top20 holders: {data['topHolders']}
    """
    url = f'{telegram_base_url}/bot{bot_token}/sendMessage?chat_id={chat_id}&text={text}'

    res = requests.post(url=url)

    if res.status_code == 200:
        print('Token address sent to telegram for autobuy!')
    else:
        print('Failed to send token address to telegram for autobuy!', res.status_code)

async def getTokensWithBackoff(signature: Signature):
    retries = 6  # Maximum number of retries
    for i in range(retries):
        try:
            return await getTokens(signature)
        except Exception as e:
            print(f"Error: {e}. Retrying in {2**i} seconds...")
            await asyncio.sleep(2**i)
    raise Exception("Exceeded maximum retries. Unable to get tokens.")

async def getTokens(signature: Signature):
    # signature = Signature.from_string(str_signature)
    transaction = solana_client.get_transaction(
        signature, encoding="jsonParsed", max_supported_transaction_version=0)
    instruction_list = transaction.value.transaction.transaction.message.instructions
    for instructions in instruction_list:
        if instructions.program_id == Pubkey.from_string(RaydiumLPV4):
            print("==================== NEW POOL DETECTED ====================")
            PairId = instructions.accounts[4]
            Token0 = instructions.accounts[8]
            Token1 = instructions.accounts[9]
            deployer = instructions.accounts[17]
            
            data = {'Token_Index': ['Token0', 'Token1', 'PairId'],
                    'Account Public Key': [Token0, Token1, PairId]}

            table = tabulate(data, headers='keys', tablefmt='fancy_grid')
            print(table)
            token_address = Token0 if str(Token0) not in sol_address else Token1

            token_info = get_metadata(solana_client, token_address, 'raydium')
            # total_supply = get_token_supply(transaction)
            total_supply = solana_client.get_token_supply(token_address).value.ui_amount_string
            token_info['totalSupply'] = total_supply
            token_info['creatorAddress'] = str(deployer)
            # token_info['pairAddress'] = str(PairId)
            # sol_price = get_pyth_solana_price()
            # token_info = _getTokenInfo(token_address=str(token_address))
            print(f"{datetime.now().strftime('%I:%M:%S %p')} - Token Info for {token_address}: {token_info}")
            logging.info(f'Token Info for {token_address}: {token_info}')
            name_checks_out = contains_word_from_list(token_info['symbol'], token_info['name'])

            if not name_checks_out and len(token_info) > 0:
                now = datetime.now()
                today = now.strftime('%Y-%m-%d')
                result = {'timestamp': now, 'address': str(token_address)}
                result.update(token_info)
                quote_token = 'token0' if Token0 != RaydiumLPV4 else 'token1'
                token_metadata = _getPairMetadata(pair_address=str(PairId), quote_token=quote_token)
                price = float(token_metadata['price']) if token_metadata['price'] else 0.0
                total_supply =  float(token_info['totalSupply']) if token_info['totalSupply'] else 0.0
                token_metadata['fdv'] = price * total_supply
                liquidity = float(token_metadata['liquidity']) if token_metadata['liquidity'] else 0.0
                result.update(token_metadata)

                print(f"{now.strftime('%I:%M:%S %p')} - Token Metadata for {token_address}: {token_metadata}")
                logging.info(f'Token Metadata for {token_address}: {token_metadata}')
                
                if (min_fdv <= token_metadata['fdv']):
                    if (liquidity >= min_liq):
                        mc_to_liq = result['fdv'] / liquidity
                        if mc_to_liq >= min_mc_to_liq:
                            file_path = f'{unfiltered_data_path}/token_addresses_unfiltered_{today}.csv'
                            # await asyncio.sleep(2)
                            save_token_address(result, file_path)
                            logging.info(f"Token address {token_address} created at {now} and saved to token_address_unfiltered_{today}.csv")
                            print(f"Token address {token_address} created at {now} and saved to token_address_unfiltered_{today}.csv")

                            check, risks, top_holders_supply_pct, top_holders_addresses_with_supply = rugcheck(token_address=token_address)
                            if check:
                                result.update({'risks': risks, 'topHoldersSupplyPct': f'{top_holders_supply_pct}%', 'topHolders': top_holders_addresses_with_supply})
                                send_contract_to_tg(token_address=token_address, data=result)
                                file_path = f'{filtered_data_path}/token_addresses_filtered_{today}.csv'
                                save_token_address(result, file_path)
                                logging.info(f"Token address {token_address} created at {now} and saved to token_address_filtered_{today}.csv")
                                print(f"Token address {token_address} created at {now} and saved to token_address_filtered_{today}.csv")
                            else:
                                logging.warning(f'Skipping {token_address} because rugcheck failed')
                                print(f'Skipping {token_address} because rugcheck failed')
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
    while True:
        try:
            async for websocket in connect(websocket_client, ping_interval=None, ssl=ssl.SSLContext(ssl.PROTOCOL_TLS)):
                subscription_id = await subscribe_to_logs(
                    websocket,
                    RpcTransactionLogsFilterMentions(Pubkey.from_string(RaydiumLPV4)),
                    Finalized
                )
                print("Subscription successful. Subscription ID:", subscription_id)
                logging.info(f"Subscription successful. Subscription ID: {subscription_id}")

                async for signature in process_messages(websocket, log_instruction):  # type: ignore
                    if signature not in seen_signatures:
                        seen_signatures.add(signature)
                        logging.info(f"{datetime.now()} - Tx: https://solscan.io/tx/{signature}")
                        print(f"{datetime.now()} - Tx: https://solscan.io/tx/{signature}")
                        await getTokensWithBackoff(signature)
                    else:
                        pass
        except (ProtocolError, ConnectionClosedError, ConnectionClosed) as err:
            # Restart socket connection if ProtocolError: invalid status code
            logging.error(err)  
            print(f"Danger!", err)
            continue

        except KeyboardInterrupt:
            print('User exited the program bye!')
            if websocket:
                await websocket.logs_unsubscribe(subscription_id)
                exit()
            
        except Exception as e:
            logging.error(f'Error exception triggered')
            print(e)

async def main():
    await run()

if __name__ == "__main__":
    asyncio.run(main())
