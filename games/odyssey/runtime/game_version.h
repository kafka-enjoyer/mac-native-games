/* Super Mario Odyssey 1.3.0 / 1.4.1 update executable (byte-identical), main build ID b424be15... .
   The build passes the update's display version (Makefile GAME_VERSION); 1.3.0 without it.
   No game-specific address is defined until it is verified. */
#pragma once
#define GAME_ODYSSEY 1
#ifndef TOTK_GAME_VERSION
#define TOTK_GAME_VERSION "1.3.0"
#endif
#define TOTK_GAME_DIR "local"
#define GAME_TITLE_ID 0x0100000000010000ULL
