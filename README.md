# Solana Listener Bot

A bot listening for token pool creation event on Raydium using websockets.

The bot uses definedfi API to retrieve information about the token and RugChecker API to determine if the token could potentially rug (mintable, suspicious token distribution, lp not locked etc).

It filters tokens with low liquidity and market cap as those tends to rug more often than others. After this intial filtering the token info is saved to a csv and some additional filtering is performed (rugcheck) to get better results.

Furthermore, the bot sends the filtered token address to telegram channel which can be scraped for automatic execution using a trading bot.