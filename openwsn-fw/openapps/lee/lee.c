#include "opendefs.h"
#include "lee.h"
#include "openqueue.h"
#include "openserial.h"
#include "packetfunctions.h"
#include "scheduler.h"
#include "IEEE802154E.h"
#include "schedule.h"
#include "icmpv6rpl.h"
#include "idmanager.h"

//=========================== variables =======================================

lee_vars_t lee_vars;

static const uint8_t lee_payload[]    = "";
static const uint8_t lee_dst_addr[]   = {
   0xbb, 0xbb, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
   0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01
};

//=========================== prototypes ======================================

void lee_timer_cb(opentimers_id_t id);
void lee_task_cb(void);

//=========================== public ==========================================

void lee_init(void) {

    // clear local variables
    memset(&lee_vars,0,sizeof(lee_vars_t));

    // register at UDP stack
    lee_vars.desc.port              = WKP_UDP_INJECT;
    lee_vars.desc.callbackReceive   = &lee_receive;
    lee_vars.desc.callbackSendDone  = &lee_sendDone;
    openudp_register(&lee_vars.desc);

    lee_vars.period = LEE_PERIOD_MS;
    // start periodic timer
    lee_vars.timerId = opentimers_create(TIMER_GENERAL_PURPOSE, TASKPRIO_UDP);
    opentimers_scheduleIn(
        lee_vars.timerId,
        LEE_PERIOD_MS,
        TIME_MS,
        TIMER_PERIODIC,
        lee_timer_cb
    );
}

void lee_sendDone(OpenQueueEntry_t* msg, owerror_t error) {

    // free the packet buffer entry
    openqueue_freePacketBuffer(msg);

    // allow send next lee packet
    lee_vars.busySendingLee = FALSE;
}

void lee_receive(OpenQueueEntry_t* pkt) {

    openqueue_freePacketBuffer(pkt);

    openserial_printError(
        COMPONENT_LEE,
        ERR_RCVD_ECHO_REPLY,
        (errorparameter_t)0,
        (errorparameter_t)0
    );
}

//=========================== private =========================================

void lee_timer_cb(opentimers_id_t id){
    // calling the task directly as the timer_cb function is executed in
    // task mode by opentimer already
    lee_task_cb();
}

void lee_task_cb(void) {
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
        opentimers_destroy(lee_vars.timerId);
        return;
    }

    foundNeighbor = icmpv6rpl_getPreferredParentEui64(&parentNeighbor);
    if (foundNeighbor==FALSE) {
        return;
    }

    if (schedule_hasManagedTxCellToNeighbor(&parentNeighbor) == FALSE) {
        return;
    }

    if (lee_vars.busySendingLee==TRUE) {
        // don't continue if I'm still sending a previous lee packet
        return;
    }

    // if you get here, send a packet

    // get a free packet buffer
    pkt = openqueue_getFreePacketBuffer(COMPONENT_LEE);
    if (pkt==NULL) {
        openserial_printError(
            COMPONENT_LEE,
            ERR_NO_FREE_PACKET_BUFFER,
            (errorparameter_t)0,
            (errorparameter_t)0
        );
        return;
    }

    pkt->owner                         = COMPONENT_LEE;
    pkt->creator                       = COMPONENT_LEE;
    pkt->l4_protocol                   = IANA_UDP;
    pkt->l4_destination_port           = WKP_UDP_INJECT;
    pkt->l4_sourcePortORicmpv6Type     = WKP_UDP_INJECT;
    pkt->l3_destinationAdd.type        = ADDR_128B;
    memcpy(&pkt->l3_destinationAdd.addr_128b[0],lee_dst_addr,16);

    // add payload
    // packetfunctions_reserveHeaderSize(pkt,sizeof(lee_payload)-1);
    // memcpy(&pkt->payload[0],lee_payload,sizeof(lee_payload)-1);

    // packetfunctions_reserveHeaderSize(pkt,sizeof(uint16_t));
    // pkt->payload[1] = (uint8_t)((lee_vars.counter & 0xff00)>>8);
    // pkt->payload[0] = (uint8_t)(lee_vars.counter & 0x00ff);
    // lee_vars.counter++;

    // packetfunctions_reserveHeaderSize(pkt,sizeof(asn_t));
    // ieee154e_getAsn(asnArray);
    // pkt->payload[0] = asnArray[0];
    // pkt->payload[1] = asnArray[1];
    // pkt->payload[2] = asnArray[2];
    // pkt->payload[3] = asnArray[3];
    // pkt->payload[4] = asnArray[4];

    packetfunctions_reserveHeaderSize(pkt,3);
    pkt->payload[0] = 'L';
    pkt->payload[1] = 'e';
    pkt->payload[2] = 'e';

    if ((openudp_send(pkt))==E_FAIL) {
        openqueue_freePacketBuffer(pkt);
    } else {
        // set busySending to TRUE
        lee_vars.busySendingLee = TRUE;
    }
}



