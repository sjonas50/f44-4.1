// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Script.sol";
import "../src/BatchAnchor.sol";

contract DeployBatchAnchor is Script {
    function run() external {
        uint256 deployerKey = vm.envUint("DEPLOYER_PRIVATE_KEY");

        vm.startBroadcast(deployerKey);
        BatchAnchor anchor = new BatchAnchor();
        vm.stopBroadcast();

        console.log("BatchAnchor deployed to:", address(anchor));
        console.log("Owner:", anchor.owner());
    }
}
