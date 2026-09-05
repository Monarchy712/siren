// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title SirenTestToken (SIRENTEST)
/// @notice Minimal, DISPOSABLE ERC-20 for generating Base Sepolia behavioral
///         activity for Siren's Phase 0 Graph data source. This is testnet demo
///         infrastructure only. It makes NO production-security claims: it is a
///         plain, standard ERC-20 that emits the standard `Transfer` event so a
///         subgraph can later index per-wallet transfer behavior.
/// @dev Self-contained (no external deps) to keep the disposable deploy simple.
contract SirenTestToken {
    string public name = "Siren Test Token";
    string public symbol = "SIRENTEST";
    uint8 public constant decimals = 18;

    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    // Standard ERC-20 events. `Transfer` is the one the subgraph indexes.
    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    /// @param initialSupply whole tokens (will be scaled by 10**decimals) minted
    ///        to the deployer. Emits a mint `Transfer` from address(0).
    constructor(uint256 initialSupply) {
        _mint(msg.sender, initialSupply * (10 ** uint256(decimals)));
    }

    /// @notice Open mint for disposable testnet seeding convenience. Not for
    ///         production — this token exists only to produce Transfer logs.
    /// @param to      recipient
    /// @param amount  amount in wei-scale (10**18 per token)
    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }

    function transfer(address to, uint256 value) external returns (bool) {
        _transfer(msg.sender, to, value);
        return true;
    }

    function approve(address spender, uint256 value) external returns (bool) {
        allowance[msg.sender][spender] = value;
        emit Approval(msg.sender, spender, value);
        return true;
    }

    function transferFrom(address from, address to, uint256 value) external returns (bool) {
        uint256 allowed = allowance[from][msg.sender];
        require(allowed >= value, "ERC20: insufficient allowance");
        if (allowed != type(uint256).max) {
            allowance[from][msg.sender] = allowed - value;
        }
        _transfer(from, to, value);
        return true;
    }

    function _transfer(address from, address to, uint256 value) internal {
        require(to != address(0), "ERC20: transfer to zero address");
        uint256 bal = balanceOf[from];
        require(bal >= value, "ERC20: insufficient balance");
        unchecked {
            balanceOf[from] = bal - value;
            balanceOf[to] += value;
        }
        emit Transfer(from, to, value);
    }

    function _mint(address to, uint256 amount) internal {
        require(to != address(0), "ERC20: mint to zero address");
        totalSupply += amount;
        unchecked {
            balanceOf[to] += amount;
        }
        emit Transfer(address(0), to, amount);
    }
}
