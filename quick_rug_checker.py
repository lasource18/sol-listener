#!usr/bin/env python3
import os
import sys
import requests
from datetime import datetime
import time
from dotenv import load_dotenv

load_dotenv()

rug_checker_url = os.environ['RUG_CHECKER_URL']
token_address = sys.argv[1]
retry_interval = 5

def main():
    url = rug_checker_url.replace('<token_address>', token_address)
    lp = None
    start_time = time.time()
    tries = 0

    while not lp or tries <= 300:
        try:
            tries += 1
            res = requests.get(url)

            if res.status_code == 200:
                data = res.json()

                if 'markets' in data.keys():
                    lp_locked_perc = data['markets'][0]['lp']['lpLockedPct']
                    if lp_locked_perc > 98.9:
                        lp = True
                        end_time = time.time()
                        break
                    else:
                        print(f'lp not fully locked. Retrying in {retry_interval} second(s).')
                        time.sleep(retry_interval)
            else:
                print(f'Request failed, Error code: {res.status_code}. Retrying in {retry_interval} second(s).')
                time.sleep(retry_interval)
        except requests.exceptions.RequestException as e:
            print(f'Request error, Error code: {res.status_code}. Retrying in {retry_interval} second(s).')
            print(e)
            time.sleep(retry_interval)
        except Exception as e:
            print(f'Exception, Error code: {res.status_code}. Retrying in {retry_interval} second(s).')
            print(e)
            time.sleep(retry_interval)
    
    run_time = start_time - end_time

    if lp:
        return f'Deployer took {run_time} seconds to lock lp for {token_address}.'
    else:
        return f'Rug checker failed to check if lp is locked for {token_address} after ~5 minutes.'

if __name__ == '__main__':
    main()