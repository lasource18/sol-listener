import os
from dotenv import load_dotenv

import requests

load_dotenv()

api_key = os.environ['DEFINEDFI_API_KEY']
url = os.environ['DEFINEDFI_URL']
solana_network_id = "1399811149"
token_address = "A6Nb2TqmXizHoz65oL3gxCKL7pCac3hXL4t1RCW3aDR5"
pair_address = "3toTYDxRoukSy4nJTiW8sYzwj5unJJARWn1jNWzTegBH"

headers = {
  "content_type":"application/json",
  "Authorization": api_key
}

def _getTokenInfo(token_address: str):
    try:
        # getNetworks = """query GetNetworksQuery { getNetworks { name id } }"""
        getTokenInfo = """query GetTokenQuery { token(input: { address: "<TOKEN_ADDRESS>", networkId: <NETWORK_ID> }) { symbol name isScam totalSupply creatorAddress socialLinks { website telegram twitter } } }"""
        getTokenInfo = getTokenInfo.replace("<TOKEN_ADDRESS>", token_address)
        getTokenInfo = getTokenInfo.replace("<NETWORK_ID>", solana_network_id)

        response = requests.post(url, headers=headers, json={"query": getTokenInfo})

        if response.status_code == 200:
            response_data = response.json().get('data', {}).get('token', {}) if response.json().get('data') else {}    
        else:
            print('_getTokenInfo | Status code:', response.status_code)
            response_data = response.json()
        
        # print(response_data)
        return {
                'symbol': response_data.get('symbol', ''),
                'name': response_data.get('name', ''),
                'isScam': response_data.get('isScam', ''),
                'totalSupply': response_data.get('totalSupply', ''),
                'creatorAddress': response_data.get('creatorAddress', ''),
                'website': response_data.get('socialLinks', {}).get('website', ''),
                'telegram': response_data.get('socialLinks', {}).get('telegram', ''),
                'twitter': response_data.get('socialLinks', {}).get('twitter', ''),
            }
        
    except Exception as e:
        print('Error in _getTokenInfo')
        print(e)
    #     print('Exiting _getTokenInfo')
    #     exit(1)

def _getPairMetadata(pair_address: str, quote_token: str):
    try:
        # getNetworks = """query GetNetworksQuery { getNetworks { name id } }"""
        getPairMetadata = """query GetPairMetadataQuery { pairMetadata(pairId:"<PAIR_ADDRESS>:<NETWORK_ID>" quoteToken:<QUOTE_TOKEN>) { pairAddress price liquidity } }"""
        getPairMetadata = getPairMetadata.replace("<PAIR_ADDRESS>", pair_address)
        getPairMetadata = getPairMetadata.replace("<NETWORK_ID>", solana_network_id)
        getPairMetadata = getPairMetadata.replace("<QUOTE_TOKEN>", quote_token)

        response = requests.post(url, headers=headers, json={"query": getPairMetadata})

        if response.status_code == 200:
            response_data = response.json()['data']['pairMetadata'] if response.json().get('data') else {}
        else:
            print('_getPairMetadata | Status code:', response.status_code)
            response_data = response.json()
        
        # print(response_data)
        
        return {
                'pairAddress': response_data.get('pairAddress', ''),
                'price': response_data.get('price', ''),
                'liquidity': response_data.get('liquidity', ''),
            }
    
    except Exception as e:
        print('Error in _getPairMetadata')
        print(e)

# _getTokenInfo(token_address)
# _getPairMetadata(pair_address, "token0")