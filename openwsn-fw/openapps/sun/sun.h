#ifndef __SUN_H
#define __SUN_H

/**
\addtogroup AppUdp
\{
\addtogroup sun
\{
*/

#include "opentimers.h"
#include "openudp.h"

//=========================== define ==========================================

#define SUN_PERIOD_MS 5000

//=========================== typedef =========================================

//=========================== variables =======================================

typedef struct {
    opentimers_id_t     timerId;   ///< periodic timer which triggers transmission
    uint16_t             counter;  ///< incrementing counter which is written into the packet
    uint16_t              period;  ///< sun packet sending period>
    udp_resource_desc_t     desc;  ///< resource descriptor for this module, used to register at UDP stack
    bool      busySendingSun;  ///< TRUE when busy sending an sun
} sun_vars_t;

//=========================== prototypes ======================================

void sun_init(void);
void sun_sendDone(OpenQueueEntry_t* msg, owerror_t error);
void sun_receive(OpenQueueEntry_t* msg);
/**
\}
\}
*/

#endif

