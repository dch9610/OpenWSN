#ifndef __LEE_H
#define __LEE_H

/**
\addtogroup AppUdp
\{
\addtogroup lee
\{
*/

#include "opentimers.h"
#include "openudp.h"

//=========================== define ==========================================

#define LEE_PERIOD_MS 5000

//=========================== typedef =========================================

//=========================== variables =======================================

typedef struct {
    opentimers_id_t     timerId;   ///< periodic timer which triggers transmission
    uint16_t             counter;  ///< incrementing counter which is written into the packet
    uint16_t              period;  ///< lee packet sending period>
    udp_resource_desc_t     desc;  ///< resource descriptor for this module, used to register at UDP stack
    bool      busySendingLee;  ///< TRUE when busy sending an lee
} lee_vars_t;

//=========================== prototypes ======================================

void lee_init(void);
void lee_sendDone(OpenQueueEntry_t* msg, owerror_t error);
void lee_receive(OpenQueueEntry_t* msg);
/**
\}
\}
*/

#endif

