WAINFLEET = """
    <alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
        <identifier>50385fcb0ab7aa447bbd46d848ce8466E</identifier>
        <sender>www.gov.uk/environment-agency</sender>
        <sent>2020-02-16T23:01:13-00:00</sent>
        <status>Actual</status>
        <msgType>Alert</msgType>
        <source>Flood warning service</source>
        <scope>Public</scope>
        <references>www.gov.uk/environment-agency,4f6d28b10ab7aa447bbd46d85f1e9effE,2020-02-16T19:20:03+00:00</references>
        <info>
            <language>en-GB</language>
            <category>Met</category>
            <event>053/055 Issue Severe Flood Warning EA</event>
            <urgency>Immediate</urgency>
            <severity>Severe</severity>
            <certainty>Likely</certainty>
            <expires>2020-02-26T23:01:14-00:00</expires>
            <senderName>Environment Agency</senderName>
            <description>A severe flood warning has been issued. Storm Dennis has resulted in significant rainfall in the Steeping River catchment with several bands of heavy rain passing through the area during today (Sunday 16 Feb). River levels along the Steeping River and the Wainfleet relief channel are expected to be similar to those in June 2019. This could result in flood embankments being overtopped. Should this happen, there is an increased risk that flood embankments could breach. It is expected that peak levels along the Steeping River in Wainfleet will be between midnight and 3am tonight. A multi-agency meeting is taking place this evening. Further messages will be issued should this be required. Do not walk on flood embankments and avoid riverside paths. Our staff are out in the area to check the flood defences and assist the emergency services and council. We will be closely monitoring the situation throughout the night. </description>
            <instruction># To check the latest information for your area - Visit [GOV.UK](https://flood-warning-information.service.gov.uk) to see the current flood warnings, view river and sea levels or check the 5-day flood risk forecast: https://flood-warning-information.service.gov.uk - Follow [@EnvAgency](https://twitter.com/EnvAgency) and [#floodaware](https://twitter.com/hashtag/floodaware) on Twitter. - Tune into weather, news and travel bulletins on local television and radio. - For access to flood warning information offline call Floodline on 0345 988 1188 using quickdial code: 307052. # What you should consider doing now - Call 999 if you are in immediate danger. - Co-operate with the emergency services and evacuate your property if told to do so. Most evacuation centres will let you bring your pets. - Act on your flood plan if you have one. - Move your family and pets to a safe place with a means of escape. - Use flood protection equipment (such as flood barriers, air brick covers and pumps) to protect your property. Unless you have proper equipment do not waste valuable time trying to keep the water out. - Move important items upstairs or to a safe place in your property, starting with cherished items of personal value that you will not be able to replace (such as family photographs). Next move valuables (such as computers), movable furniture and furnishings. - You may need to leave your property, so pack a bag with enough items for a few nights away. Include essential items including a torch with spare batteries, mobile phone and charger, warm clothes, home insurance information, water, food, first aid kit and any prescription medicines or baby care items you may need. - Turn off gas, electricity and water mains supplies before flood water starts to enter your property. Never touch an electrical switch if you are standing in water. - If it is safe to do so, make sure neighbours are aware of the situation and offer help to anyone who may need it. - Avoid walking, cycling or driving through flood water - 30 cm of fast-flowing water can move a car and 6 inches can knock an adult off their feet. - Flood water is dangerous and may be polluted. Wash your hands thoroughly if you’ve been in contact with it. ##### Businesses - Act on your business flood plan if you have one. - Move your staff and customers to a safe place with a means of escape. - Move stock and other valuable items upstairs or to a safe place in your building. For media enquiries please contact our media teams: https://www.gov.uk/government/organisations/environment-agency/about/media-enquiries </instruction>
            <web>https://flood-warning-information.service.gov.uk</web>
            <contact>0345 988 1188</contact>
            <area>
                <areaDesc>River Steeping in Wainfleet All Saints</areaDesc>
                <polygon>53.10569,0.24453 53.10593,0.24430 53.10601,0.24375 53.10615,0.24349 53.10629,0.24356 53.10656,0.24336 53.10697,0.24354 53.10684,0.24298 53.10694,0.24264 53.10721,0.24302 53.10752,0.24310 53.10777,0.24308 53.10805,0.24320 53.10803,0.24187 53.10776,0.24085 53.10774,0.24062 53.10702,0.24056 53.10679,0.24088 53.10658,0.24071 53.10651,0.24049 53.10656,0.24022 53.10642,0.24022 53.10632,0.24052 53.10629,0.24082 53.10612,0.24093 53.10583,0.24133 53.10564,0.24178 53.10541,0.24282 53.10569,0.24453</polygon>
                <geocode>
                    <valueName>TargetAreaCode</valueName>
                    <value>053FWFSTEEP4</value>
                </geocode>
            </area>
        </info>
    </alert>
"""

UPDATE = """
    <alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
      <identifier>PAAQ-4-mg5a94</identifier>
      <sender>wcatwc@noaa.gov</sender>
      <sent>2013-01-05T10:58:23-00:00</sent>
      <status>Actual</status>
      <msgType>Update</msgType>
      <source>WCATWC</source>
      <scope>Public</scope>
      <code>IPAWSv1.0</code>
      <references>wcatwc@noaa.gov,PAAQ-1-mg5a94,2013-01-05T09:01:16-00:00 wcatwc@noaa.gov,PAAQ-2-mg5a94,2013-01-05T09:30:16-00:00 wcatwc@noaa.gov,PAAQ-3-mg5a94,2013-01-05T10:17:31-00:00</references>
      <incidents>mg5a94</incidents>
      <info>
        <category>Geo</category>
        <event>Tsunami Cancellation</event>
        <responseType>None</responseType>
        <urgency>Past</urgency>
        <severity>Unknown</severity>
        <certainty>Unlikely</certainty>
        <onset>2013-01-05T10:58:23-00:00</onset>
        <expires>2013-01-05T10:58:23-00:00</expires>
        <senderName>NWS West Coast/Alaska Tsunami Warning Center Palmer AK</senderName>
        <headline>The tsunami Warning is canceled for the coastal areas of British Columbia and Alaska from the north tip of Vancouver Island, British Columbia to Cape Fairweather, Alaska (80 miles SE of Yakutat).</headline>
        <description>The tsunami Warning is canceled for the coastal areas of British Columbia and Alaska from the north tip of Vancouver Island, British Columbia to Cape Fairweather, Alaska (80 miles SE of Yakutat). - Event details: Preliminary magnitude 7.5 (Mw) earthquake / Lat: 55.300, Lon: -134.900 at 2013-01-05T08:58:20Z Tsunami cancellations indicate the end of the damaging tsunami threat.  A cancellation is issued after an evaluation of sea level data confirms that a destructive tsunami will not impact the alerted region, or after tsunami levels have subsided to non-damaging levels. </description>
        <instruction>Recommended Actions:   Do not re-occupy hazard zones until local emergency officials indicate it is safe to do so. This will be the last West Coast/Alaska Tsunami Warning Center message issued for this event.  Refer to the internet site ntwc.arh.noaa.gov for more information. </instruction>
        <web>http://ntwc.arh.noaa.gov/events/PAAQ/2013/01/05/mg5a94/4/WEAK51/WEAK51.txt</web>
        <parameter>
          <valueName>EventLocationName</valueName>
          <value>95 miles NW of Dixon Entrance, Alaska</value>
        </parameter>
        <parameter>
          <valueName>EventPreliminaryMagnitude</valueName>
          <value>7.5</value>
        </parameter>
        <parameter>
          <valueName>EventPreliminaryMagnitudeType</valueName>
          <value>Mw</value>
        </parameter>
        <parameter>
          <valueName>EventOriginTime</valueName>
          <value>2013-01-05T08:58:20-00:00</value>
        </parameter>
        <parameter>
          <valueName>EventDepth</valueName>
          <value>5 kilometers</value>
        </parameter>
        <parameter>
          <valueName>EventLatLon</valueName>
          <value>55.300,-134.900 0.000</value>
        </parameter>
        <parameter>
          <valueName>VTEC</valueName>
          <value>/O.CAN.PAAQ.TS.W.0001.000000T0000Z-000000T0000Z/</value>
        </parameter>
        <parameter>
          <valueName>NWSUGC</valueName>
          <value>BCZ220-210-922-912-921-911-110-AKZ026&gt;029-023-024-019&gt;022-025-051258-</value>
        </parameter>
        <parameter>
          <valueName>ProductDefinition</valueName>
          <value>Tsunami cancellations indicate the end of the damaging tsunami threat.  A cancellation is issued after an evaluation of sea level data confirms that a destructive tsunami will not impact the alerted region, or after tsunami levels have subsided to non-damaging levels. </value>
        </parameter>
        <parameter>
          <valueName>WEAK51</valueName>
          <value>Public Tsunami Warnings, Watches, and Advisories for AK, BC, and US West Coast</value>
        </parameter>
        <parameter>
          <valueName>EAS-ORG</valueName>
          <value>WXR</value>
        </parameter>
        <resource>
          <resourceDesc>Event Data as a JSON document</resourceDesc>
          <mimeType>application/json</mimeType>
          <uri>http://ntwc.arh.noaa.gov/events/PAAQ/2013/01/05/mg5a94/4/WEAK51/PAAQ.json</uri>
        </resource>
        <area>
          <areaDesc>95 miles NW of Dixon Entrance, Alaska</areaDesc>
          <circle>55.3,-134.9 0.0</circle>
        </area>
      </info>
    </alert>
"""

CANCEL = """
    <alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
      <identifier>PAAQ-4-mg5a94</identifier>
      <sender>wcatwc@noaa.gov</sender>
      <sent>2013-01-05T10:58:23-00:00</sent>
      <status>Actual</status>
      <msgType>Cancel</msgType>
      <source>WCATWC</source>
      <scope>Public</scope>
      <code>IPAWSv1.0</code>
      <references>wcatwc@noaa.gov,PAAQ-1-mg5a94,2013-01-05T09:01:16-00:00 wcatwc@noaa.gov,PAAQ-2-mg5a94,2013-01-05T09:30:16-00:00 wcatwc@noaa.gov,PAAQ-3-mg5a94,2013-01-05T10:17:31-00:00</references>
      <incidents>mg5a94</incidents>
      <info>
        <category>Geo</category>
        <event>Tsunami Cancellation</event>
        <responseType>None</responseType>
        <urgency>Past</urgency>
        <severity>Unknown</severity>
        <certainty>Unlikely</certainty>
        <onset>2013-01-05T10:58:23-00:00</onset>
        <expires>2013-01-05T10:58:23-00:00</expires>
        <senderName>NWS West Coast/Alaska Tsunami Warning Center Palmer AK</senderName>
        <headline>The tsunami Warning is canceled for the coastal areas of British Columbia and Alaska from the north tip of Vancouver Island, British Columbia to Cape Fairweather, Alaska (80 miles SE of Yakutat).</headline>
        <description>The tsunami Warning is canceled for the coastal areas of British Columbia and Alaska from the north tip of Vancouver Island, British Columbia to Cape Fairweather, Alaska (80 miles SE of Yakutat). - Event details: Preliminary magnitude 7.5 (Mw) earthquake / Lat: 55.300, Lon: -134.900 at 2013-01-05T08:58:20Z Tsunami cancellations indicate the end of the damaging tsunami threat.  A cancellation is issued after an evaluation of sea level data confirms that a destructive tsunami will not impact the alerted region, or after tsunami levels have subsided to non-damaging levels. </description>
        <instruction>Recommended Actions:   Do not re-occupy hazard zones until local emergency officials indicate it is safe to do so. This will be the last West Coast/Alaska Tsunami Warning Center message issued for this event.  Refer to the internet site ntwc.arh.noaa.gov for more information. </instruction>
        <web>http://ntwc.arh.noaa.gov/events/PAAQ/2013/01/05/mg5a94/4/WEAK51/WEAK51.txt</web>
        <parameter>
          <valueName>EventLocationName</valueName>
          <value>95 miles NW of Dixon Entrance, Alaska</value>
        </parameter>
        <parameter>
          <valueName>EventPreliminaryMagnitude</valueName>
          <value>7.5</value>
        </parameter>
        <parameter>
          <valueName>EventPreliminaryMagnitudeType</valueName>
          <value>Mw</value>
        </parameter>
        <parameter>
          <valueName>EventOriginTime</valueName>
          <value>2013-01-05T08:58:20-00:00</value>
        </parameter>
        <parameter>
          <valueName>EventDepth</valueName>
          <value>5 kilometers</value>
        </parameter>
        <parameter>
          <valueName>EventLatLon</valueName>
          <value>55.300,-134.900 0.000</value>
        </parameter>
        <parameter>
          <valueName>VTEC</valueName>
          <value>/O.CAN.PAAQ.TS.W.0001.000000T0000Z-000000T0000Z/</value>
        </parameter>
        <parameter>
          <valueName>NWSUGC</valueName>
          <value>BCZ220-210-922-912-921-911-110-AKZ026&gt;029-023-024-019&gt;022-025-051258-</value>
        </parameter>
        <parameter>
          <valueName>ProductDefinition</valueName>
          <value>Tsunami cancellations indicate the end of the damaging tsunami threat.  A cancellation is issued after an evaluation of sea level data confirms that a destructive tsunami will not impact the alerted region, or after tsunami levels have subsided to non-damaging levels. </value>
        </parameter>
        <parameter>
          <valueName>WEAK51</valueName>
          <value>Public Tsunami Warnings, Watches, and Advisories for AK, BC, and US West Coast</value>
        </parameter>
        <parameter>
          <valueName>EAS-ORG</valueName>
          <value>WXR</value>
        </parameter>
        <resource>
          <resourceDesc>Event Data as a JSON document</resourceDesc>
          <mimeType>application/json</mimeType>
          <uri>http://ntwc.arh.noaa.gov/events/PAAQ/2013/01/05/mg5a94/4/WEAK51/PAAQ.json</uri>
        </resource>
        <area>
          <areaDesc>95 miles NW of Dixon Entrance, Alaska</areaDesc>
          <circle>55.3,-134.9 0.0</circle>
        </area>
      </info>
    </alert>
"""
