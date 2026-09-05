import { Address, BigInt, Bytes, ethereum } from "@graphprotocol/graph-ts"
import { Transfer } from "../generated/SirenTestToken/SirenTestToken"
import { Account, Counterparty } from "../generated/schema"

const ZERO = Address.zero()
const ONE = BigInt.fromI32(1)

function loadOrCreate(addr: Address, block: ethereum.Block): Account {
  let acct = Account.load(addr)
  if (acct == null) {
    acct = new Account(addr)
    acct.firstSeenBlock = block.number
    acct.firstSeenTimestamp = block.timestamp
    acct.lastSeenBlock = block.number
    acct.lastSeenTimestamp = block.timestamp
    acct.txCount = BigInt.zero()
    acct.sentCount = BigInt.zero()
    acct.receivedCount = BigInt.zero()
    acct.uniqueCounterparties = BigInt.zero()
    acct.operator = null
  }
  return acct as Account
}

// Count `other` as a distinct counterparty of `acct` exactly once.
function trackCounterparty(acct: Account, other: Address): void {
  if (other.equals(ZERO)) return
  let pairId = acct.id.concat(other as Bytes)
  if (Counterparty.load(pairId) == null) {
    let cp = new Counterparty(pairId)
    cp.save()
    acct.uniqueCounterparties = acct.uniqueCounterparties.plus(ONE)
  }
}

export function handleTransfer(event: Transfer): void {
  let from = event.params.from
  let to = event.params.to
  let block = event.block

  // Sender side (skip the zero address, i.e. mint source).
  if (!from.equals(ZERO)) {
    let sender = loadOrCreate(from, block)
    sender.txCount = sender.txCount.plus(ONE)
    sender.sentCount = sender.sentCount.plus(ONE)
    sender.lastSeenBlock = block.number
    sender.lastSeenTimestamp = block.timestamp
    trackCounterparty(sender, to)
    sender.save()
  }

  // Receiver side (skip the zero address, i.e. burn dest).
  if (!to.equals(ZERO)) {
    let receiver = loadOrCreate(to, block)
    receiver.txCount = receiver.txCount.plus(ONE)
    receiver.receivedCount = receiver.receivedCount.plus(ONE)
    receiver.lastSeenBlock = block.number
    receiver.lastSeenTimestamp = block.timestamp
    // Operator = sender of the first inbound transfer (funding source).
    if (receiver.operator === null && !from.equals(ZERO)) {
      receiver.operator = from
    }
    trackCounterparty(receiver, from)
    receiver.save()
  }
}
