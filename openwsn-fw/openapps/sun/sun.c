#include "opendefs.h"
#include "sun.h"
#include "openqueue.h"
#include "openserial.h"
#include "packetfunctions.h"
#include "scheduler.h"
#include "IEEE802154E.h"
#include "schedule.h"
#include "icmpv6rpl.h"
#include "idmanager.h"

//=========================== variables =======================================

sun_vars_t sun_vars;

static const uint8_t sun_payload[]    = "";
static const uint8_t sun_dst_addr[]   = {
   0xbb, 0xbb, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
   0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01
};

//=========================== prototypes ======================================

void sun_timer_cb(opentimers_id_t id);
void sun_task_cb(void);

//=========================== public ==========================================

void sun_init(void) {

    // clear local variables
    memset(&sun_vars,0,sizeof(sun_vars_t));

    // register at UDP stack
    sun_vars.desc.port              = WKP_UDP_INJECT;
    sun_vars.desc.callbackReceive   = &sun_receive;
    sun_vars.desc.callbackSendDone  = &sun_sendDone;
    openudp_register(&sun_vars.desc);

    sun_vars.period = SUN_PERIOD_MS;
    // start periodic timer
    sun_vars.timerId = opentimers_create(TIMER_GENERAL_PURPOSE, TASKPRIO_UDP);
    opentimers_scheduleIn(
        sun_vars.timerId,
        SUN_PERIOD_MS,
        TIME_MS,
        TIMER_PERIODIC,
        sun_timer_cb
    );
}

void sun_sendDone(OpenQueueEntry_t* msg, owerror_t error) {

    // free the packet buffer entry
    openqueue_freePacketBuffer(msg);

    // allow send next sun packet
    sun_vars.busySendingSun = FALSE;
}

void sun_receive(OpenQueueEntry_t* pkt) {

    openqueue_freePacketBuffer(pkt);

    openserial_printError(
        COMPONENT_SUN,
        ERR_RCVD_ECHO_REPLY,
        (errorparameter_t)0,
        (errorparameter_t)0
    );
}

//=========================== private =========================================

void sun_timer_cb(opentimers_id_t id){
    // calling the task directly as the timer_cb function is executed in
    // task mode by opentimer already
    sun_task_cb();
}

void sun_task_cb(void) {
    OpenQueueEntry_t*    pkt;
    uint8_t              asnArray[5];
    open_addr_t          parentNeighbor;
    bool                 foundNeighbor;

    // don't run if not synch
    if (ieee154e_isSynch() == FALSE) {
        return;
    }

    // don't run on dagroot
    if (idmanager_getIsDAGroot()) {
        opentimers_destroy(sun_vars.timerId);
        return;
    }

    foundNeighbor = icmpv6rpl_getPreferredParentEui64(&parentNeighbor);
    if (foundNeighbor==FALSE) {
        return;
    }

    if (schedule_hasManagedTxCellToNeighbor(&parentNeighbor) == FALSE) {
        return;
    }

    if (sun_vars.busySendingSun==TRUE) {
        // don't continue if I'm still sending a previous sun packet
        return;
    }

    // if you get here, send a packet

    // get a free packet buffer
    pkt = openqueue_getFreePacketBuffer(COMPONENT_SUN);
    if (pkt==NULL) {
        openserial_printError(
            COMPONENT_SUN,
            ERR_NO_FREE_PACKET_BUFFER,
            (errorparameter_t)0,
            (errorparameter_t)0
        );
        return;
    }

    pkt->owner                         = COMPONENT_SUN;
    pkt->creator                       = COMPONENT_SUN;
    pkt->l4_protocol                   = IANA_UDP;
    pkt->l4_destination_port           = WKP_UDP_INJECT;
    pkt->l4_sourcePortORicmpv6Type     = WKP_UDP_INJECT;
    pkt->l3_destinationAdd.type        = ADDR_128B;
    memcpy(&pkt->l3_destinationAdd.addr_128b[0],sun_dst_addr,16);

    // add payload
    // packetfunctions_reserveHeaderSize(pkt,sizeof(sun_payload)-1);
    // memcpy(&pkt->payload[0],sun_payload,sizeof(sun_payload)-1);

    // packetfunctions_reserveHeaderSize(pkt,sizeof(uint16_t));
    // pkt->payload[1] = (uint8_t)((sun_vars.counter & 0xff00)>>8);
    // pkt->payload[0] = (uint8_t)(sun_vars.counter & 0x00ff);
    // sun_vars.counter++;

    // packetfunctions_reserveHeaderSize(pkt,sizeof(asn_t));
    // ieee154e_getAsn(asnArray);
    // pkt->payload[0] = asnArray[0];
    // pkt->payload[1] = asnArray[1];
    // pkt->payload[2] = asnArray[2];
    // pkt->payload[3] = asnArray[3];
    // pkt->payload[4] = asnArray[4];

    packetfunctions_reserveHeaderSize(pkt,3);
    pkt->payload[0] = 'S';
    pkt->payload[1] = 'U';
    pkt->payload[2] = 'N';

    if ((openudp_send(pkt))==E_FAIL) {
        openqueue_freePacketBuffer(pkt);
    } else {
        // set busySending to TRUE
        sun_vars.busySendingSun = TRUE;
    }
}



