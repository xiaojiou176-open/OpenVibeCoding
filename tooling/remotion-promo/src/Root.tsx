import {Composition} from "remotion";
import {OpenVibeCodingTeaser} from "./Teaser";

export const RemotionRoot = () => {
  return (
    <>
      <Composition
        id="OpenVibeCodingTeaser"
        component={OpenVibeCodingTeaser}
        width={1280}
        height={720}
        fps={30}
        durationInFrames={540}
        defaultProps={{}}
      />
    </>
  );
};
